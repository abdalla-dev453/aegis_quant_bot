//+------------------------------------------------------------------+
//|                                                AegisQuantEA.mq5  |
//|                        Copyright 2026, AegisQuant Technologies.  |
//|                             https://aegisquant.internal-systems  |
//+------------------------------------------------------------------+
#property copyright   "Copyright 2026, AegisQuant Technologies."
#property link        "https://aegisquant.internal-systems"
#property version     "2.00"
#property description "Instrument-Grade MetaTrader 5 AI Bridge & Dual-Layer Risk Execution Engine"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>
#include <Trade\SymbolInfo.mqh>

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                 |
//+------------------------------------------------------------------+
input group "=== Cloud Bridge Connectivity ==="
input string   InpServerUrl               = "http://127.0.0.1:8000"; // AegisQuant API Base URL
input string   InpPairingCode             = "";                     // 8-Character Pairing Code (First Run)
input int      InpHeartbeatSec            = 5;                      // Heartbeat & Telemetry Interval (sec)
input int      InpSignalPollSec           = 1;                      // Signal Polling Interval (sec)
input int      InpWebRequestTimeoutMs     = 2500;                   // Network Timeout (<=3000 ms)

input group "=== Local Terminal Risk Limits (Final Gatekeeper) ==="
input int      InpMaxSignalDeviationPts   = 30;                     // Max Price Deviation (points)
input double   InpMaxDailyLossPct         = 2.0;                    // Max Daily Loss Floor (% of Balance)
input int      InpMaxOpenPositions        = 5;                      // Max Concurrent Open Positions
input ulong    InpMagicNumber             = 884400;                 // Magic Number for Orders
input bool     InpAutoExecuteDefault      = false;                  // Local Auto-Execute Initial State
input int      InpMaxSpreadPts            = 30;                     // Max Allowed Spread Filter (points)

input group "=== Active Trade Management (Trailing, BE & Scale-Out) ==="
input bool     InpEnableBreakEven         = true;                   // Move SL to Break-Even at +1R
input double   InpBreakEvenTriggerR       = 1.0;                    // Break-Even Trigger (R-Multiple)
input int      InpBreakEvenBufferPts      = 5;                      // Break-Even Profit Buffer (points)
input bool     InpEnableTrailingStop      = true;                   // Dynamic Trailing Stop
input int      InpTrailingStopPts         = 150;                    // Trailing Stop Distance (points)
input int      InpTrailingStepPts         = 20;                     // Trailing Step (points)
input bool     InpEnablePartialTP         = true;                   // Scale-Out Partial Close at 1R
input double   InpPartialTPRatio          = 0.5;                    // Partial Close Ratio (0.5 = 50%)

input group "=== Session Protections ==="
input bool     InpAutoCloseFriday         = false;                  // Auto-Close Positions on Friday
input int      InpFridayCloseHour         = 21;                     // Friday Close Hour (UTC)

//+------------------------------------------------------------------+
//| CONSTANTS & ENUMS                                                |
//+------------------------------------------------------------------+
#define DEVICE_FILE "aegis_quant_device.dat"
#define COMMENT_PREFIX "AQ:"

enum ENUM_BRIDGE_STATE
{
   BRIDGE_NOT_PAIRED,
   BRIDGE_CONNECTING,
   BRIDGE_CONNECTED,
   BRIDGE_STALE,
   BRIDGE_OFFLINE
};

//+------------------------------------------------------------------+
//| SIMPLE STRING UTILITIES & SHA256 / HMAC HELPERS                  |
//+------------------------------------------------------------------+
class CHelpers
{
public:
   static string ToHex(const uchar &data[])
   {
      string result = "";
      int size = ArraySize(data);
      for(int i = 0; i < size; i++)
      {
         result += StringFormat("%02x", data[i]);
      }
      return result;
   }

   static string Sha256(const string text)
   {
      uchar src[];
      uchar dst[];
      uchar key[];
      ArrayResize(key, 0);
      StringToCharArray(text, src, 0, WHOLE_ARRAY, CP_UTF8);
      int len = ArraySize(src) - 1;
      if(len < 0) len = 0;
      ArrayResize(src, len);

      CryptEncode(CRYPT_HASH_SHA256, src, key, dst);
      return ToHex(dst);
   }

   static string HmacSha256(const string keyStr, const string message)
   {
      uchar key[];
      uchar src[];
      uchar dst[];
      StringToCharArray(keyStr, key, 0, WHOLE_ARRAY, CP_ACP);
      int klen = ArraySize(key) - 1;
      if(klen < 0) klen = 0;
      ArrayResize(key, klen);

      StringToCharArray(message, src, 0, WHOLE_ARRAY, CP_UTF8);
      int slen = ArraySize(src) - 1;
      if(slen < 0) slen = 0;
      ArrayResize(src, slen);

      CryptEncode(CRYPT_HASH_SHA256, src, key, dst);
      return ToHex(dst);
   }

   static string GenerateNonce()
   {
      return StringFormat("%I64u_%d", GetMicrosecondCount(), MathRand());
   }

   static string EscapeJson(const string str)
   {
      string res = str;
      StringReplace(res, "\\", "\\\\");
      StringReplace(res, "\"", "\\\"");
      StringReplace(res, "\r", "");
      StringReplace(res, "\n", "\\n");
      return res;
   }

   static string ExtractJsonValue(const string json, const string key)
   {
      string pattern = "\"" + key + "\":\"";
      int start = StringFind(json, pattern);
      if(start >= 0)
      {
         start += StringLen(pattern);
         int end = StringFind(json, "\"", start);
         if(end > start)
            return StringSubstr(json, start, end - start);
      }

      // Check numeric/boolean
      pattern = "\"" + key + "\":";
      start = StringFind(json, pattern);
      if(start >= 0)
      {
         start += StringLen(pattern);
         int end1 = StringFind(json, ",", start);
         int end2 = StringFind(json, "}", start);
         int end = (end1 > 0 && end1 < end2) ? end1 : end2;
         if(end > start)
         {
            string val = StringSubstr(json, start, end - start);
            StringTrimLeft(val);
            StringTrimRight(val);
            return val;
         }
      }
      return "";
   }
};

//+------------------------------------------------------------------+
//| CBRIDGE CLASS: AUTHENTICATED NETWORK COMMUNICATION               |
//+------------------------------------------------------------------+
class CBridge
{
private:
   string            m_serverUrl;
   string            m_deviceId;
   string            m_deviceToken;
   ENUM_BRIDGE_STATE m_state;
   datetime          m_lastHeartbeatSent;
   datetime          m_lastSignalPoll;
   int               m_backoffSec;
   int               m_consecutiveFailures;
   bool              m_localAutoExecute;
   bool              m_serverAutoExecute;
   bool              m_killSwitchActive;

   // Last received signal cache
   string            m_lastSignalId;
   string            m_lastSignalSymbol;
   string            m_lastSignalSide;
   double            m_lastSignalConf;
   datetime          m_lastSignalTime;

public:
   CBridge() : m_state(BRIDGE_NOT_PAIRED),
               m_lastHeartbeatSent(0),
               m_lastSignalPoll(0),
               m_backoffSec(1),
               m_consecutiveFailures(0),
               m_localAutoExecute(false),
               m_serverAutoExecute(false),
               m_killSwitchActive(false),
               m_lastSignalConf(0),
               m_lastSignalTime(0)
   {
   }

   bool Initialize(const string serverUrl, const string pairingCode, const bool autoExec)
   {
      m_serverUrl = serverUrl;
      m_localAutoExecute = autoExec;

      // Remove trailing slash if present
      if(StringSubstr(m_serverUrl, StringLen(m_serverUrl) - 1) == "/")
         m_serverUrl = StringSubstr(m_serverUrl, 0, StringLen(m_serverUrl) - 1);

      // Check for saved credentials
      if(LoadCredentials())
      {
         m_state = BRIDGE_CONNECTING;
         Print("[AegisQuant] Persisted device credentials loaded. Device ID: ", m_deviceId);
         return true;
      }

      // If pairing code supplied, perform pairing
      if(StringLen(pairingCode) >= 8)
      {
         return Pair(pairingCode);
      }

      m_state = BRIDGE_NOT_PAIRED;
      Print("[AegisQuant] No credentials found. Enter InpPairingCode in EA settings.");
      return false;
   }

   bool LoadCredentials()
   {
      if(!FileIsExist(DEVICE_FILE, 0))
         return false;

      int handle = FileOpen(DEVICE_FILE, FILE_READ | FILE_BIN);
      if(handle == INVALID_HANDLE)
         return false;

      uint devIdLen = FileReadInteger(handle, INT_VALUE);
      m_deviceId = FileReadString(handle, devIdLen);
      uint tokLen = FileReadInteger(handle, INT_VALUE);
      m_deviceToken = FileReadString(handle, tokLen);
      FileClose(handle);

      return (StringLen(m_deviceId) > 0 && StringLen(m_deviceToken) > 0);
   }

   bool SaveCredentials(const string devId, const string token)
   {
      int handle = FileOpen(DEVICE_FILE, FILE_WRITE | FILE_BIN);
      if(handle == INVALID_HANDLE)
         return false;

      FileWriteInteger(handle, StringLen(devId), INT_VALUE);
      FileWriteString(handle, devId);
      FileWriteInteger(handle, StringLen(token), INT_VALUE);
      FileWriteString(handle, token);
      FileClose(handle);

      m_deviceId = devId;
      m_deviceToken = token;
      return true;
   }

   bool Pair(const string code)
   {
      string endpoint = m_serverUrl + "/ea/v1/pair";
      string accountId = IntegerToString(AccountInfoInteger(ACCOUNT_LOGIN));
      string maskedAcc = StringSubstr(accountId, 0, 4) + "****" + StringSubstr(accountId, StringLen(accountId) - 2);

      string jsonPayload = StringFormat(
         "{\"code\":\"%s\",\"terminal_build\":\"%d\",\"broker\":\"%s\",\"server\":\"%s\",\"account_number_masked\":\"%s\",\"account_currency\":\"%s\",\"leverage\":%d}",
         CHelpers::EscapeJson(code),
         TerminalInfoInteger(TERMINAL_BUILD),
         CHelpers::EscapeJson(AccountInfoString(ACCOUNT_COMPANY)),
         CHelpers::EscapeJson(AccountInfoString(ACCOUNT_SERVER)),
         CHelpers::EscapeJson(maskedAcc),
         AccountInfoString(ACCOUNT_CURRENCY),
         AccountInfoInteger(ACCOUNT_LEVERAGE)
      );

      char postData[];
      char result[];
      string resultHeaders;
      StringToCharArray(jsonPayload, postData, 0, WHOLE_ARRAY, CP_UTF8);
      int len = ArraySize(postData) - 1;
      ArrayResize(postData, (len < 0) ? 0 : len);

      string headers = "Content-Type: application/json\r\n";
      ResetLastError();
      int res = WebRequest("POST", endpoint, headers, InpWebRequestTimeoutMs, postData, result, resultHeaders);

      if(res == 200)
      {
         string response = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
         string devId = CHelpers::ExtractJsonValue(response, "device_id");
         string devTok = CHelpers::ExtractJsonValue(response, "device_token");

         if(StringLen(devId) > 0 && StringLen(devTok) > 0)
         {
            SaveCredentials(devId, devTok);
            m_state = BRIDGE_CONNECTED;
            Print("[AegisQuant] Pairing successful! Device registered.");
            return true;
         }
      }

      Print("[AegisQuant] Pairing failed. HTTP: ", res, " Err: ", GetLastError());
      return false;
   }

   bool SendAuthenticatedRequest(const string method, const string path, const string body, string &responseOut, int &httpStatusOut)
   {
      if(m_state == BRIDGE_NOT_PAIRED || StringLen(m_deviceToken) == 0)
         return false;

      string fullUrl = m_serverUrl + path;
      string timestamp = IntegerToString(TimeCurrent());
      string nonce = CHelpers::GenerateNonce();
      string bodyHash = CHelpers::Sha256(body);

      // Canonical Request: METHOD\nPATH\nTIMESTAMP\nNONCE\nBODY_HASH
      string canonical = method + "\n" + path + "\n" + timestamp + "\n" + nonce + "\n" + bodyHash;
      string signature = CHelpers::HmacSha256(m_deviceToken, canonical);

      string headers = "Content-Type: application/json\r\n" +
                       "X-EA-Device-Token: " + m_deviceToken + "\r\n" +
                       "X-EA-Timestamp: " + timestamp + "\r\n" +
                       "X-EA-Nonce: " + nonce + "\r\n" +
                       "X-EA-Signature: " + signature + "\r\n";

      char postData[];
      char result[];
      string resultHeaders;
      StringToCharArray(body, postData, 0, WHOLE_ARRAY, CP_UTF8);
      int len = ArraySize(postData) - 1;
      ArrayResize(postData, (len < 0) ? 0 : len);

      ResetLastError();
      int res = WebRequest(method, fullUrl, headers, InpWebRequestTimeoutMs, postData, result, resultHeaders);
      httpStatusOut = res;

      if(res == 200 || res == 201)
      {
         responseOut = CharArrayToString(result, 0, WHOLE_ARRAY, CP_UTF8);
         m_consecutiveFailures = 0;
         m_backoffSec = 1;
         m_state = BRIDGE_CONNECTED;
         return true;
      }

      m_consecutiveFailures++;
      m_backoffSec = MathMin(60, (int)MathPow(2, MathMin(6, m_consecutiveFailures)));
      m_state = (m_consecutiveFailures > 3) ? BRIDGE_OFFLINE : BRIDGE_STALE;
      return false;
   }

   void SendHeartbeat()
   {
      if(TimeCurrent() - m_lastHeartbeatSent < InpHeartbeatSec)
         return;

      m_lastHeartbeatSent = TimeCurrent();

      // Build positions JSON array
      string positionsJson = "[";
      int totalPos = PositionsTotal();
      int added = 0;

      for(int i = 0; i < totalPos; i++)
      {
         CPositionInfo pos;
         if(pos.SelectByIndex(i))
         {
            if(added > 0) positionsJson += ",";
            positionsJson += StringFormat(
               "{\"external_position_id\":\"%I64u\",\"symbol\":\"%s\",\"side\":\"%s\",\"volume\":\"%.2f\",\"entry_price\":\"%.5f\",\"current_price\":\"%.5f\",\"stop_loss\":%s,\"take_profit\":%s,\"unrealized_pnl\":\"%.2f\",\"swap\":\"%.2f\",\"observed_at\":\"%s\"}",
               pos.Ticket(),
               pos.Symbol(),
               (pos.PositionType() == POSITION_TYPE_BUY ? "BUY" : "SELL"),
               pos.Volume(),
               pos.PriceOpen(),
               pos.PriceCurrent(),
               (pos.StopLoss() > 0 ? StringFormat("\"%.5f\"", pos.StopLoss()) : "null"),
               (pos.TakeProfit() > 0 ? StringFormat("\"%.5f\"", pos.TakeProfit()) : "null"),
               pos.Profit(),
               pos.Swap(),
               TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS)
            );
            added++;
         }
      }
      positionsJson += "]";

      double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      double equity = AccountInfoDouble(ACCOUNT_EQUITY);
      double margin = AccountInfoDouble(ACCOUNT_MARGIN);
      double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      double marginLevel = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);

      string payload = StringFormat(
         "{\"snapshot\":{\"balance\":\"%.2f\",\"equity\":\"%.2f\",\"margin\":\"%.2f\",\"free_margin\":\"%.2f\",\"margin_level\":%s,\"open_positions_count\":%d,\"account_currency\":\"%s\",\"leverage\":%d,\"captured_at\":\"%s\"},\"positions\":%s}",
         balance,
         equity,
         margin,
         freeMargin,
         (marginLevel > 0 ? StringFormat("\"%.2f\"", marginLevel) : "null"),
         totalPos,
         AccountInfoString(ACCOUNT_CURRENCY),
         AccountInfoInteger(ACCOUNT_LEVERAGE),
         TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
         positionsJson
      );

      string response;
      int status;
      if(SendAuthenticatedRequest("POST", "/ea/v1/heartbeat", payload, response, status))
      {
         string autoEx = CHelpers::ExtractJsonValue(response, "auto_execute");
         m_serverAutoExecute = (autoEx == "true");
         string killSw = CHelpers::ExtractJsonValue(response, "kill_switch");
         m_killSwitchActive = (killSw == "true");
      }
   }

   void PollSignals(CTrade &tradeEngine)
   {
      if(TimeCurrent() - m_lastSignalPoll < InpSignalPollSec)
         return;

      m_lastSignalPoll = TimeCurrent();

      string response;
      int status;
      if(!SendAuthenticatedRequest("GET", "/ea/v1/signals", "", response, status))
         return;

      // Check if signals returned
      if(StringLen(response) < 10 || response == "[]")
         return;

      // Extract single signal item
      string sigId = CHelpers::ExtractJsonValue(response, "signal_id");
      string symbol = CHelpers::ExtractJsonValue(response, "symbol");
      string action = CHelpers::ExtractJsonValue(response, "action");
      double refPrice = StringToDouble(CHelpers::ExtractJsonValue(response, "reference_price"));
      double volume = StringToDouble(CHelpers::ExtractJsonValue(response, "volume"));
      double sl = StringToDouble(CHelpers::ExtractJsonValue(response, "stop_loss"));
      double tp = StringToDouble(CHelpers::ExtractJsonValue(response, "take_profit"));
      double conf = StringToDouble(CHelpers::ExtractJsonValue(response, "confidence"));
      int maxDev = (int)StringToInteger(CHelpers::ExtractJsonValue(response, "max_deviation_points"));

      if(StringLen(sigId) == 0)
         return;

      m_lastSignalId = sigId;
      m_lastSignalSymbol = symbol;
      m_lastSignalSide = action;
      m_lastSignalConf = conf;
      m_lastSignalTime = TimeCurrent();

      // Execute Signal through strict 8-step pipeline
      ExecuteSignalPipeline(tradeEngine, sigId, symbol, action, refPrice, volume, sl, tp, conf, maxDev);
   }

   void ExecuteSignalPipeline(
      CTrade &tradeEngine,
      const string sigId,
      const string symbol,
      const string action,
      const double refPrice,
      const double volume,
      const double sl,
      const double tp,
      const double confidence,
      const int maxDevPoints
   )
   {
      string commentTag = COMMENT_PREFIX + sigId;

      // Step 0: Check if signal already executed (Deduplication across restarts)
      if(IsSignalAlreadyExecuted(sigId))
      {
         SendSignalAck(sigId, "ACKED", "Already executed or recorded");
         return;
      }

      // Step 1: Check Auto-Execute Toggle (Stricter setting wins)
      if(!m_localAutoExecute || !m_serverAutoExecute)
      {
         SendSignalAck(sigId, "REJECTED", "AUTO_EXECUTE_DISABLED");
         return;
      }

      // Step 2: Emergency Kill Switch Active
      if(m_killSwitchActive)
      {
         SendSignalAck(sigId, "REJECTED", "KILL_SWITCH_ACTIVE");
         return;
      }

      // Step 3: Symbol selection and subscription
      CSymbolInfo symInfo;
      if(!symInfo.Name(symbol) || !symInfo.Select())
      {
         SendSignalAck(sigId, "REJECTED", "SYMBOL_DISALLOWED");
         return;
      }
      symInfo.RefreshRates();

      // Step 3.1: Spread Spike Filter
      if(symInfo.Spread() > InpMaxSpreadPts)
      {
         SendSignalAck(sigId, "REJECTED", StringFormat("SPREAD_TOO_HIGH: %d pts > %d limit", symInfo.Spread(), InpMaxSpreadPts));
         return;
      }

      // Step 4: Price Deviation Check
      bool isBuy = (action == "BUY");
      double curPrice = isBuy ? symInfo.Ask() : symInfo.Bid();
      double devPoints = MathAbs(curPrice - refPrice) / symInfo.Point();
      int allowedDev = (maxDevPoints > 0) ? maxDevPoints : InpMaxSignalDeviationPts;

      if(devPoints > allowedDev)
      {
         SendSignalAck(sigId, "REJECTED", StringFormat("PRICE_DEVIATION: %.1f pts > %d limit", devPoints, allowedDev));
         return;
      }

      // Step 5: Daily Loss Floor Check
      if(IsDailyLossExceeded())
      {
         SendSignalAck(sigId, "REJECTED", "DAILY_LOSS_LIMIT_REACHED");
         return;
      }

      // Step 6: Max Positions Check
      if(PositionsTotal() >= InpMaxOpenPositions)
      {
         SendSignalAck(sigId, "REJECTED", "MAX_POSITIONS_REACHED");
         return;
      }

      // Step 7: Free Margin Check
      double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      double reqMargin = 0;
      if(!OrderCalcMargin((isBuy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL), symbol, volume, curPrice, reqMargin) || reqMargin > freeMargin * 0.8)
      {
         SendSignalAck(sigId, "REJECTED", "INSUFFICIENT_MARGIN");
         return;
      }

      // Step 8: Execute OrderSend()
      tradeEngine.SetExpertMagicNumber(InpMagicNumber);
      tradeEngine.SetDeviationInPoints(allowedDev);

      bool ok = false;
      if(isBuy)
         ok = tradeEngine.Buy(volume, symbol, curPrice, sl, tp, commentTag);
      else
         ok = tradeEngine.Sell(volume, symbol, curPrice, sl, tp, commentTag);

      if(ok)
      {
         ulong ticket = tradeEngine.ResultOrder();
         double execPrice = tradeEngine.ResultPrice();
         SendSignalAck(sigId, "EXECUTED", "Order placed successfully", execPrice, volume);
         SendTradeReport(sigId, ticket, symbol, action, volume, execPrice, sl, tp);
         Print("[AegisQuant] Signal executed successfully. Ticket: ", ticket);
      }
      else
      {
         string err = StringFormat("ORDER_SEND_FAILED: Retcode %d", tradeEngine.ResultRetcode());
         SendSignalAck(sigId, "REJECTED", err);
         Print("[AegisQuant] OrderSend failed: ", err);
      }
   }

   bool IsSignalAlreadyExecuted(const string sigId)
   {
      string tag = COMMENT_PREFIX + sigId;

      // Check active open positions
      for(int i = 0; i < PositionsTotal(); i++)
      {
         CPositionInfo pos;
         if(pos.SelectByIndex(i) && StringFind(pos.Comment(), tag) >= 0)
            return true;
      }

      // Check historical orders from today
      datetime start = iTime(_Symbol, PERIOD_D1, 0);
      HistorySelect(start, TimeCurrent());
      for(int i = 0; i < HistoryOrdersTotal(); i++)
      {
         ulong ticket = HistoryOrderGetTicket(i);
         if(ticket > 0 && StringFind(HistoryOrderGetString(ticket, ORDER_COMMENT), tag) >= 0)
            return true;
      }

      return false;
   }

   bool IsDailyLossExceeded()
   {
      datetime todayStart = iTime(_Symbol, PERIOD_D1, 0);
      HistorySelect(todayStart, TimeCurrent());

      double realizedToday = 0;
      for(int i = 0; i < HistoryDealsTotal(); i++)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket > 0)
            realizedToday += HistoryDealGetDouble(ticket, DEAL_PROFIT) + HistoryDealGetDouble(ticket, DEAL_SWAP) + HistoryDealGetDouble(ticket, DEAL_COMMISSION);
      }

      double floatingPnl = 0;
      for(int i = 0; i < PositionsTotal(); i++)
      {
         CPositionInfo pos;
         if(pos.SelectByIndex(i))
            floatingPnl += pos.Profit() + pos.Swap();
      }

      double totalTodayPnl = realizedToday + floatingPnl;
      double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      if(balance <= 0) return true;

      double lossPct = (-totalTodayPnl / balance) * 100.0;
      return (totalTodayPnl < 0 && lossPct >= InpMaxDailyLossPct);
   }

   void SendSignalAck(const string sigId, const string event, const string reason, const double execPrice = 0, const double execVol = 0)
   {
      string path = "/ea/v1/signals/" + sigId + "/ack";
      string payload = StringFormat(
         "{\"event\":\"%s\",\"occurred_at\":\"%s\",\"reason\":\"%s\",\"reason_code\":\"%s\"%s%s}",
         event,
         TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
         CHelpers::EscapeJson(reason),
         CHelpers::EscapeJson(reason),
         (execPrice > 0 ? StringFormat(",\"execution_price\":\"%.5f\"", execPrice) : ""),
         (execVol > 0 ? StringFormat(",\"execution_volume\":\"%.2f\"", execVol) : "")
      );

      string resp;
      int status;
      SendAuthenticatedRequest("POST", path, payload, resp, status);
   }

   void SendTradeReport(const string sigId, const ulong ticket, const string symbol, const string side, const double volume, const double price, const double sl, const double tp)
   {
      string payload = StringFormat(
         "{\"signal_id\":\"%s\",\"ticket\":\"%I64u\",\"symbol\":\"%s\",\"side\":\"%s\",\"volume\":\"%.2f\",\"execution_price\":\"%.5f\",\"opened_at\":\"%s\"}",
         sigId,
         ticket,
         symbol,
         side,
         volume,
         price,
         TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS)
      );

      string resp;
      int status;
      SendAuthenticatedRequest("POST", "/ea/v1/trade-reports", payload, resp, status);
   }

   void FlattenAllPositions(CTrade &tradeEngine)
   {
      Print("[AegisQuant] Emergency KILL SWITCH triggered. Flattening all positions...");
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         CPositionInfo pos;
         if(pos.SelectByIndex(i))
         {
            tradeEngine.PositionClose(pos.Ticket());
         }
      }
   }

   void ManageActivePositions(CTrade &tradeEngine)
   {
      // 1. Check Friday auto-close window
      if(InpAutoCloseFriday)
      {
         MqlDateTime dt;
         TimeCurrent(dt);
         if(dt.day_of_week == 5 && dt.hour >= InpFridayCloseHour)
         {
            Print("[AegisQuant] Friday auto-close window active. Flattening intraday positions.");
            FlattenAllPositions(tradeEngine);
            return;
         }
      }

      // 2. Scan and manage open positions
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         CPositionInfo pos;
         if(!pos.SelectByIndex(i)) continue;
         if(pos.Magic() != InpMagicNumber) continue;

         string symbol = pos.Symbol();
         CSymbolInfo symInfo;
         if(!symInfo.Name(symbol) || !symInfo.Select()) continue;
         symInfo.RefreshRates();

         double point = symInfo.Point();
         double openPrice = pos.PriceOpen();
         double curPrice = (pos.PositionType() == POSITION_TYPE_BUY) ? symInfo.Bid() : symInfo.Ask();
         double sl = pos.StopLoss();
         double tp = pos.TakeProfit();
         double volume = pos.Volume();
         ulong ticket = pos.Ticket();

         if(pos.PositionType() == POSITION_TYPE_BUY)
         {
            double profitPts = (curPrice - openPrice) / point;
            double riskPts = (sl > 0) ? (openPrice - sl) / point : 100.0;
            if(riskPts <= 0) riskPts = 100.0;

            // A. Break-Even Check (+1R)
            if(InpEnableBreakEven && profitPts >= (InpBreakEvenTriggerR * riskPts))
            {
               double beSL = openPrice + InpBreakEvenBufferPts * point;
               if(sl < beSL)
               {
                  if(tradeEngine.PositionModify(ticket, beSL, tp))
                  {
                     PrintFormat("[AegisQuant] Break-Even moved for BUY #%I64u at %.5f", ticket, beSL);
                     sl = beSL;
                  }
               }
            }

            // B. Trailing Stop Check
            if(InpEnableTrailingStop && profitPts >= InpTrailingStopPts)
            {
               double trailSL = curPrice - InpTrailingStopPts * point;
               if(trailSL > sl + InpTrailingStepPts * point && trailSL > openPrice)
               {
                  if(tradeEngine.PositionModify(ticket, trailSL, tp))
                  {
                     PrintFormat("[AegisQuant] Trailing Stop updated for BUY #%I64u at %.5f", ticket, trailSL);
                  }
               }
            }

            // C. Scale-out partial close at +1R
            if(InpEnablePartialTP && profitPts >= riskPts && StringFind(pos.Comment(), "[SCALED]") < 0)
            {
               double closeVol = NormalizeDouble(volume * InpPartialTPRatio, 2);
               double minLot = symInfo.LotsMin();
               double lotStep = symInfo.LotsStep();
               closeVol = MathFloor(closeVol / lotStep) * lotStep;

               if(closeVol >= minLot && closeVol < volume)
               {
                  if(tradeEngine.PositionClosePartial(ticket, closeVol))
                  {
                     PrintFormat("[AegisQuant] Scaled-out %.2f lots at +1R for BUY #%I64u", closeVol, ticket);
                  }
               }
            }
         }
         else if(pos.PositionType() == POSITION_TYPE_SELL)
         {
            double profitPts = (openPrice - curPrice) / point;
            double riskPts = (sl > 0) ? (sl - openPrice) / point : 100.0;
            if(riskPts <= 0) riskPts = 100.0;

            // A. Break-Even Check (+1R)
            if(InpEnableBreakEven && profitPts >= (InpBreakEvenTriggerR * riskPts))
            {
               double beSL = openPrice - InpBreakEvenBufferPts * point;
               if(sl == 0 || sl > beSL)
               {
                  if(tradeEngine.PositionModify(ticket, beSL, tp))
                  {
                     PrintFormat("[AegisQuant] Break-Even moved for SELL #%I64u at %.5f", ticket, beSL);
                     sl = beSL;
                  }
               }
            }

            // B. Trailing Stop Check
            if(InpEnableTrailingStop && profitPts >= InpTrailingStopPts)
            {
               double trailSL = curPrice + InpTrailingStopPts * point;
               if((sl == 0 || trailSL < sl - InpTrailingStepPts * point) && trailSL < openPrice)
               {
                  if(tradeEngine.PositionModify(ticket, trailSL, tp))
                  {
                     PrintFormat("[AegisQuant] Trailing Stop updated for SELL #%I64u at %.5f", ticket, trailSL);
                  }
               }
            }

            // C. Scale-out partial close at +1R
            if(InpEnablePartialTP && profitPts >= riskPts && StringFind(pos.Comment(), "[SCALED]") < 0)
            {
               double closeVol = NormalizeDouble(volume * InpPartialTPRatio, 2);
               double minLot = symInfo.LotsMin();
               double lotStep = symInfo.LotsStep();
               closeVol = MathFloor(closeVol / lotStep) * lotStep;

               if(closeVol >= minLot && closeVol < volume)
               {
                  if(tradeEngine.PositionClosePartial(ticket, closeVol))
                  {
                     PrintFormat("[AegisQuant] Scaled-out %.2f lots at +1R for SELL #%I64u", closeVol, ticket);
                  }
               }
            }
         }
      }
   }

   // State & Panel accessors
   ENUM_BRIDGE_STATE GetState() const { return m_state; }
   bool IsLocalAutoExecute() const { return m_localAutoExecute; }
   void ToggleLocalAutoExecute() { m_localAutoExecute = !m_localAutoExecute; }
   bool IsKillSwitchActive() const { return m_killSwitchActive; }
   void GetLastSignal(string &sym, string &side, double &conf, datetime &time)
   {
      sym = m_lastSignalSymbol;
      side = m_lastSignalSide;
      conf = m_lastSignalConf;
      time = m_lastSignalTime;
   }
};

//+------------------------------------------------------------------+
//| GLOBAL VARIABLES                                                 |
//+------------------------------------------------------------------+
CBridge g_bridge;
CTrade  g_trade;

//+------------------------------------------------------------------+
//| DRAWING THE ON-CHART INSTRUMENT PANEL                            |
//+------------------------------------------------------------------+
void RenderDashboardPanel()
{
   string fontName = "Segoe UI";
   int x = 20;
   int y = 30;
   int w = 280;
   int h = 180;

   // Main Panel Background
   ObjectCreate(0, "AQ_BG", OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, "AQ_BG", OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, "AQ_BG", OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, "AQ_BG", OBJPROP_XSIZE, w);
   ObjectSetInteger(0, "AQ_BG", OBJPROP_YSIZE, h);
   ObjectSetInteger(0, "AQ_BG", OBJPROP_BGCOLOR, C'17,19,26'); // #11131A
   ObjectSetInteger(0, "AQ_BG", OBJPROP_BORDER_COLOR, C'35,39,52'); // #232734
   ObjectSetInteger(0, "AQ_BG", OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, "AQ_BG", OBJPROP_CORNER, CORNER_LEFT_UPPER);

   // Title
   ObjectCreate(0, "AQ_TITLE", OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, "AQ_TITLE", OBJPROP_XDISTANCE, x + 12);
   ObjectSetInteger(0, "AQ_TITLE", OBJPROP_YDISTANCE, y + 10);
   ObjectSetString(0, "AQ_TITLE", OBJPROP_TEXT, "AEGIS QUANT BRIDGE v2.0");
   ObjectSetString(0, "AQ_TITLE", OBJPROP_FONT, fontName);
   ObjectSetInteger(0, "AQ_TITLE", OBJPROP_FONTSIZE, 9);
   ObjectSetInteger(0, "AQ_TITLE", OBJPROP_COLOR, C'248,250,252');

   // Connection Pill
   ENUM_BRIDGE_STATE state = g_bridge.GetState();
   string statusText = "NOT PAIRED";
   color statusColor = C'148,163,184';
   if(state == BRIDGE_CONNECTED) { statusText = "CONNECTED"; statusColor = C'16,185,129'; }
   else if(state == BRIDGE_STALE) { statusText = "STALE"; statusColor = C'245,158,11'; }
   else if(state == BRIDGE_OFFLINE) { statusText = "OFFLINE"; statusColor = C'244,63,94'; }

   ObjectCreate(0, "AQ_STATUS", OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, "AQ_STATUS", OBJPROP_XDISTANCE, x + 12);
   ObjectSetInteger(0, "AQ_STATUS", OBJPROP_YDISTANCE, y + 32);
   ObjectSetString(0, "AQ_STATUS", OBJPROP_TEXT, "Status: " + statusText);
   ObjectSetString(0, "AQ_STATUS", OBJPROP_FONT, fontName);
   ObjectSetInteger(0, "AQ_STATUS", OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, "AQ_STATUS", OBJPROP_COLOR, statusColor);

   // Auto Execute Status
   string autoText = g_bridge.IsLocalAutoExecute() ? "AI AUTO: ENABLED" : "AI AUTO: DISABLED";
   color autoColor = g_bridge.IsLocalAutoExecute() ? C'16,185,129' : C'148,163,184';

   ObjectCreate(0, "AQ_AUTO", OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, "AQ_AUTO", OBJPROP_XDISTANCE, x + 12);
   ObjectSetInteger(0, "AQ_AUTO", OBJPROP_YDISTANCE, y + 50);
   ObjectSetString(0, "AQ_AUTO", OBJPROP_TEXT, autoText);
   ObjectSetString(0, "AQ_AUTO", OBJPROP_FONT, fontName);
   ObjectSetInteger(0, "AQ_AUTO", OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, "AQ_AUTO", OBJPROP_COLOR, autoColor);

   // Last Signal Info
   string sym, side;
   double conf;
   datetime sigTime;
   g_bridge.GetLastSignal(sym, side, conf, sigTime);
   string sigText = "Last Signal: None";
   if(StringLen(sym) > 0)
   {
      int age = (int)(TimeCurrent() - sigTime);
      sigText = StringFormat("Last: %s %s (%.0f%%) %ds ago", sym, side, conf * 100, age);
   }

   ObjectCreate(0, "AQ_SIGNAL", OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, "AQ_SIGNAL", OBJPROP_XDISTANCE, x + 12);
   ObjectSetInteger(0, "AQ_SIGNAL", OBJPROP_YDISTANCE, y + 70);
   ObjectSetString(0, "AQ_SIGNAL", OBJPROP_TEXT, sigText);
   ObjectSetString(0, "AQ_SIGNAL", OBJPROP_FONT, fontName);
   ObjectSetInteger(0, "AQ_SIGNAL", OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, "AQ_SIGNAL", OBJPROP_COLOR, C'203,213,225');

   // Auto Toggle Button
   ObjectCreate(0, "AQ_BTN_AUTO", OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, "AQ_BTN_AUTO", OBJPROP_XDISTANCE, x + 12);
   ObjectSetInteger(0, "AQ_BTN_AUTO", OBJPROP_YDISTANCE, y + 95);
   ObjectSetInteger(0, "AQ_BTN_AUTO", OBJPROP_XSIZE, 120);
   ObjectSetInteger(0, "AQ_BTN_AUTO", OBJPROP_YSIZE, 24);
   ObjectSetString(0, "AQ_BTN_AUTO", OBJPROP_TEXT, "TOGGLE AUTO");
   ObjectSetString(0, "AQ_BTN_AUTO", OBJPROP_FONT, fontName);
   ObjectSetInteger(0, "AQ_BTN_AUTO", OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, "AQ_BTN_AUTO", OBJPROP_BGCOLOR, C'37,99,235'); // #2563EB
   ObjectSetInteger(0, "AQ_BTN_AUTO", OBJPROP_COLOR, clrWhite);

   // Emergency Kill Button
   ObjectCreate(0, "AQ_BTN_KILL", OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, "AQ_BTN_KILL", OBJPROP_XDISTANCE, x + 140);
   ObjectSetInteger(0, "AQ_BTN_KILL", OBJPROP_YDISTANCE, y + 95);
   ObjectSetInteger(0, "AQ_BTN_KILL", OBJPROP_XSIZE, 120);
   ObjectSetInteger(0, "AQ_BTN_KILL", OBJPROP_YSIZE, 24);
   ObjectSetString(0, "AQ_BTN_KILL", OBJPROP_TEXT, "EMERGENCY KILL");
   ObjectSetString(0, "AQ_BTN_KILL", OBJPROP_FONT, fontName);
   ObjectSetInteger(0, "AQ_BTN_KILL", OBJPROP_FONTSIZE, 8);
   ObjectSetInteger(0, "AQ_BTN_KILL", OBJPROP_BGCOLOR, C'244,63,94'); // #F43F5E
   ObjectSetInteger(0, "AQ_BTN_KILL", OBJPROP_COLOR, clrWhite);

   ChartRedraw();
}

void RemoveDashboardPanel()
{
   ObjectDelete(0, "AQ_BG");
   ObjectDelete(0, "AQ_TITLE");
   ObjectDelete(0, "AQ_STATUS");
   ObjectDelete(0, "AQ_AUTO");
   ObjectDelete(0, "AQ_SIGNAL");
   ObjectDelete(0, "AQ_BTN_AUTO");
   ObjectDelete(0, "AQ_BTN_KILL");
   ChartRedraw();
}

//+------------------------------------------------------------------+
//| EXPERT INITIALIZATION                                            |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("[AegisQuant] Initializing EA Bridge v2.0 with Active Trade Management...");

   g_bridge.Initialize(InpServerUrl, InpPairingCode, InpAutoExecuteDefault);
   RenderDashboardPanel();

   EventSetTimer(1); // 1-second timer loop for polling and heartbeat
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EXPERT DEINITIALIZATION                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   RemoveDashboardPanel();
   Print("[AegisQuant] Deinitialized reason: ", reason);
}

//+------------------------------------------------------------------+
//| ON TIMER: HEARTBEAT, SIGNAL POLLING & POSITION MANAGEMENT        |
//+------------------------------------------------------------------+
void OnTimer()
{
   g_bridge.SendHeartbeat();
   g_bridge.PollSignals(g_trade);
   g_bridge.ManageActivePositions(g_trade);

   if(g_bridge.IsKillSwitchActive())
   {
      g_bridge.FlattenAllPositions(g_trade);
   }

   RenderDashboardPanel();
}

//+------------------------------------------------------------------+
//| ON TICK: REAL-TIME TRAILING STOP & BREAK-EVEN UPDATES            |
//+------------------------------------------------------------------+
void OnTick()
{
   g_bridge.ManageActivePositions(g_trade);
}

//+------------------------------------------------------------------+
//| ON CHART EVENT: UI BUTTON INTERACTIONS                           |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
   if(id == CHARTEVENT_OBJECT_CLICK)
   {
      if(sparam == "AQ_BTN_AUTO")
      {
         g_bridge.ToggleLocalAutoExecute();
         RenderDashboardPanel();
         Print("[AegisQuant] Local AI Auto Toggled: ", g_bridge.IsLocalAutoExecute());
      }
      else if(sparam == "AQ_BTN_KILL")
      {
         g_bridge.FlattenAllPositions(g_trade);
         RenderDashboardPanel();
         Print("[AegisQuant] Emergency KILL clicked from chart panel.");
      }
   }
}

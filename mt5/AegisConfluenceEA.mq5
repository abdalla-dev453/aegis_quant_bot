#property copyright "Aegis Quant"
#property version   "1.00"
#property strict

#include <Trade/Trade.mqh>

input string   InpSymbol            = "";                     // Empty uses current chart symbol
input ENUM_TIMEFRAMES InpTriggerTF  = PERIOD_H1;             // Signal trigger timeframe
input ENUM_TIMEFRAMES InpBiasTF     = PERIOD_H4;             // Bias timeframe
input int      InpSlowEma           = 200;
input int      InpFastEma           = 50;
input int      InpRsiPeriod         = 14;
input int      InpAtrPeriod         = 14;
input double   InpRiskPerTradePct   = 1.5;
input double   InpAtrStopMult       = 1.5;
input double   InpAtrTpMult         = 3.0;
input int      InpMaxConcurrentPositions = 3;
input ulong    InpMagicNumber       = 990011;
input int      InpDeviationPoints   = 20;
input int      InpBarsToLoad        = 400;
input bool     InpAllowBuy          = true;
input bool     InpAllowSell         = true;
input bool     InpUseNewsBlackout   = true;
input int      InpNewsBlackoutMinutes = 30;
input datetime InpNextNewsTimestamp = 0;

CTrade trade;
string g_symbol = "";
datetime g_lastBarTime = 0;

struct SignalInfo
{
   int direction;
   double atr;
   double entry;
   double sl;
   double tp;
   string reason;
};

int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpDeviationPoints);
   trade.SetTypeFilling(ORDER_FILLING_IOC);

   g_symbol = StringLen(InpSymbol) > 0 ? InpSymbol : _Symbol;
   if(!SymbolSelect(g_symbol, true))
   {
      PrintFormat("EA init failed: could not select symbol '%s'.", g_symbol);
      return(INIT_FAILED);
   }

   if(!IsMarketOpenAndTradeable(g_symbol))
   {
      PrintFormat("EA init failed: symbol '%s' is not tradeable on this broker/server.", g_symbol);
      return(INIT_FAILED);
   }

   // Warm start: the first candle time will trigger an evaluation once a new closed bar arrives.
   g_lastBarTime = 0;
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   // Intentionally left blank for a minimal scaffold.
   // In a fuller implementation, release the indicator handles here.
}

void OnTick()
{
   if(StringLen(g_symbol) == 0)
      return;

   if(!IsMarketOpenAndTradeable(g_symbol))
      return;

   if(IsNewsBlackoutActive())
   {
      PrintFormat("[AegisQuant] News blackout active for %s; skipping new entry.", g_symbol);
      return;
   }

   if(!IsNewClosedBar(g_symbol, InpTriggerTF, g_lastBarTime))
      return;

   SignalInfo signal = EvaluateSignal(g_symbol);
   if(signal.direction == 0)
      return;

   if(!TradeAllowedForDirection(signal.direction))
      return;

   if(!ValidateTradeContext(g_symbol, signal.entry, signal.sl, signal.tp))
   {
      PrintFormat("Trade context rejected for %s: %s", g_symbol, signal.reason);
      return;
   }

   double lotSize = CalculateLotSize(g_symbol, MathAbs(signal.entry - signal.sl));
   if(lotSize <= 0.0)
   {
      PrintFormat("Risk sizing rejected for %s: %s", g_symbol, signal.reason);
      return;
   }

   int orderType = signal.direction > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double price = signal.entry;
   if(signal.direction > 0)
      price = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   else
      price = SymbolInfoDouble(g_symbol, SYMBOL_BID);

   if(price <= 0.0)
      return;

   bool sent = SendOrder(g_symbol, orderType, price, signal.sl, signal.tp, lotSize, signal.reason);
   if(sent)
      PrintFormat("Order sent: %s %s lots=%.2f entry=%.5f sl=%.5f tp=%.5f",
                  g_symbol,
                  signal.direction > 0 ? "BUY" : "SELL",
                  lotSize,
                  price,
                  signal.sl,
                  signal.tp);
}

bool IsMarketOpenAndTradeable(string symbol)
{
   if(!SymbolSelect(symbol, true))
      return false;

   int tradeMode = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   if(tradeMode != SYMBOL_TRADE_MODE_FULL)
      return false;

   return SymbolInfoDouble(symbol, SYMBOL_ASK) > 0.0 && SymbolInfoDouble(symbol, SYMBOL_BID) > 0.0;
}

bool IsNewsBlackoutActive()
{
   if(!InpUseNewsBlackout)
      return false;

   if(InpNextNewsTimestamp <= 0)
      return false;

   datetime now = TimeCurrent();
   datetime startWindow = InpNextNewsTimestamp - InpNewsBlackoutMinutes * 60;
   datetime endWindow = InpNextNewsTimestamp + InpNewsBlackoutMinutes * 60;

   return now >= startWindow && now <= endWindow;
}

bool IsNewClosedBar(string symbol, ENUM_TIMEFRAMES tf, datetime &lastBarTime)
{
   datetime currentTime = (datetime)SeriesInfoInteger(symbol, tf, SERIES_LASTBAR_DATE);
   if(currentTime <= 0)
      return false;

   if(lastBarTime == 0 || currentTime > lastBarTime)
   {
      lastBarTime = currentTime;
      return true;
   }

   return false;
}

SignalInfo EvaluateSignal(string symbol)
{
   SignalInfo sig = {0,0.0,0.0,0.0,0.0,""};

   MqlRates h1[];
   MqlRates h4[];
   ArraySetAsSeries(h1, true);
   ArraySetAsSeries(h4, true);

   int h1Copied = CopyRates(symbol, InpTriggerTF, 0, InpBarsToLoad, h1);
   int h4Copied = CopyRates(symbol, InpBiasTF, 0, InpBarsToLoad, h4);

   if(h1Copied < InpBarsToLoad || h4Copied < InpBarsToLoad)
   {
      sig.reason = "Insufficient bars downloaded from broker/server";
      return sig;
   }

   double emaFastH1[];
   double emaSlowH1[];
   double emaFastH4[];
   double emaSlowH4[];
   double rsiH1[];
   double atrH1[];
   ArraySetAsSeries(emaFastH1, true);
   ArraySetAsSeries(emaSlowH1, true);
   ArraySetAsSeries(emaFastH4, true);
   ArraySetAsSeries(emaSlowH4, true);
   ArraySetAsSeries(rsiH1, true);
   ArraySetAsSeries(atrH1, true);

   int emaFastHandleH1 = iMA(symbol, InpTriggerTF, InpFastEma, 0, MODE_EMA, PRICE_CLOSE);
   int emaSlowHandleH1 = iMA(symbol, InpTriggerTF, InpSlowEma, 0, MODE_EMA, PRICE_CLOSE);
   int emaFastHandleH4 = iMA(symbol, InpBiasTF, InpFastEma, 0, MODE_EMA, PRICE_CLOSE);
   int emaSlowHandleH4 = iMA(symbol, InpBiasTF, InpSlowEma, 0, MODE_EMA, PRICE_CLOSE);
   int rsiHandleH1 = iRSI(symbol, InpTriggerTF, InpRsiPeriod, PRICE_CLOSE);
   int atrHandleH1 = iATR(symbol, InpTriggerTF, InpAtrPeriod);

   if(emaFastHandleH1 == INVALID_HANDLE || emaSlowHandleH1 == INVALID_HANDLE ||
      emaFastHandleH4 == INVALID_HANDLE || emaSlowHandleH4 == INVALID_HANDLE ||
      rsiHandleH1 == INVALID_HANDLE || atrHandleH1 == INVALID_HANDLE)
   {
      sig.reason = "Indicator handles failed to initialize";
      return sig;
   }

   int copied = CopyBuffer(emaFastHandleH1, 0, 0, 3, emaFastH1);
   copied += CopyBuffer(emaSlowHandleH1, 0, 0, 3, emaSlowH1);
   copied += CopyBuffer(emaFastHandleH4, 0, 0, 3, emaFastH4);
   copied += CopyBuffer(emaSlowHandleH4, 0, 0, 3, emaSlowH4);
   copied += CopyBuffer(rsiHandleH1, 0, 0, 3, rsiH1);
   copied += CopyBuffer(atrHandleH1, 0, 0, 3, atrH1);

   IndicatorRelease(emaFastHandleH1);
   IndicatorRelease(emaSlowHandleH1);
   IndicatorRelease(emaFastHandleH4);
   IndicatorRelease(emaSlowHandleH4);
   IndicatorRelease(rsiHandleH1);
   IndicatorRelease(atrHandleH1);

   if(copied < 6)
   {
      sig.reason = "Indicator buffer sync incomplete";
      return sig;
   }

   double fastH1 = emaFastH1[0];
   double slowH1 = emaSlowH1[0];
   double fastH4 = emaFastH4[0];
   double slowH4 = emaSlowH4[0];
   double rsi = rsiH1[0];
   double atr = atrH1[0];

   if(!isfinite(fastH1) || !isfinite(slowH1) || !isfinite(fastH4) || !isfinite(slowH4) || !isfinite(rsi) || !isfinite(atr) || atr <= 0.0)
   {
      sig.reason = "Indicator data degenerate / invalid";
      return sig;
   }

   double sentimentScore = 0.0;
   bool newsBlackout = IsNewsBlackoutActive();

   bool longBias = fastH4 > slowH4;
   bool shortBias = fastH4 < slowH4;
   bool longTrigger = fastH1 > slowH1;
   bool shortTrigger = fastH1 < slowH1;
   bool rsiLongConfirm = rsi >= 52.0 && rsi < 70.0;
   bool rsiShortConfirm = rsi <= 48.0 && rsi > 30.0;

   if(longBias && longTrigger && rsiLongConfirm && sentimentScore >= 0.5 && !newsBlackout)
   {
      sig.direction = 1;
      sig.atr = atr;
      sig.entry = SymbolInfoDouble(symbol, SYMBOL_ASK);
      sig.sl = sig.entry - MathMax(atr * InpAtrStopMult, GetBrokerStopLevel(symbol) * SymbolInfoDouble(symbol, SYMBOL_POINT));
      sig.tp = sig.entry + (atr * InpAtrTpMult);
      sig.reason = "Multi-timeframe bullish confluence";
      return sig;
   }

   if(shortBias && shortTrigger && rsiShortConfirm && sentimentScore <= -0.5 && !newsBlackout)
   {
      sig.direction = -1;
      sig.atr = atr;
      sig.entry = SymbolInfoDouble(symbol, SYMBOL_BID);
      sig.sl = sig.entry + MathMax(atr * InpAtrStopMult, GetBrokerStopLevel(symbol) * SymbolInfoDouble(symbol, SYMBOL_POINT));
      sig.tp = sig.entry - (atr * InpAtrTpMult);
      sig.reason = "Multi-timeframe bearish confluence";
      return sig;
   }

   sig.reason = "No valid signal";
   return sig;
}

bool TradeAllowedForDirection(int direction)
{
   if(direction > 0)
      return InpAllowBuy;
   if(direction < 0)
      return InpAllowSell;
   return false;
}

double CalculateLotSize(string symbol, double slDistanceInPrice)
{
   if(slDistanceInPrice <= 0.0)
      return 0.0;

   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0)
      return 0.0;

   double riskAmount = equity * (InpRiskPerTradePct / 100.0);
   double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tickSize <= 0.0 || tickValue <= 0.0)
      return 0.0;

   double slDistanceTicks = slDistanceInPrice / tickSize;
   double valuePerLot = slDistanceTicks * tickValue;
   if(valuePerLot <= 0.0)
      return 0.0;

   double rawLots = riskAmount / valuePerLot;
   double volumeStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   if(volumeStep <= 0.0)
      volumeStep = 0.01;

   double lots = MathFloor(rawLots / volumeStep) * volumeStep;
   double minLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   if(minLot > 0.0)
      lots = MathMax(lots, minLot);
   if(maxLot > 0.0)
      lots = MathMin(lots, maxLot);

   return lots;
}

bool ValidateTradeContext(string symbol, double entryPrice, double slPrice, double tpPrice)
{
   int tradeMode = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   if(tradeMode != SYMBOL_TRADE_MODE_FULL)
      return false;

   int stopLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freezeLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);

   if(stopLevel > 0)
   {
      double minAllowed = stopLevel * point;
      if(MathAbs(entryPrice - slPrice) < minAllowed || MathAbs(tpPrice - entryPrice) < minAllowed)
         return false;
   }

   if(freezeLevel > 0)
   {
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      if(MathAbs(ask - bid) > freezeLevel * point)
         return false;
   }

   return entryPrice > 0.0 && slPrice > 0.0 && tpPrice > 0.0;
}

double GetBrokerStopLevel(string symbol)
{
   int stopLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(stopLevel <= 0 || point <= 0.0)
      return 0.0;
   return stopLevel * point;
}

bool SendOrder(string symbol, int orderType, double price, double sl, double tp, double volume, string comment)
{
   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};

   ZeroMemory(request);
   ZeroMemory(result);

   request.action      = TRADE_ACTION_DEAL;
   request.magic       = InpMagicNumber;
   request.symbol      = symbol;
   request.volume      = volume;
   request.type        = orderType;
   request.price       = price;
   request.sl          = sl;
   request.tp          = tp;
   request.deviation   = InpDeviationPoints;
   request.comment     = comment;
   request.type_filling = ORDER_FILLING_IOC;
   request.type_time    = ORDER_TIME_GTC;

   bool sent = trade.OrderSend(request, result);
   if(!sent)
   {
      PrintFormat("OrderSend returned false for %s: retcode=%d comment=%s", symbol, result.retcode, result.comment);
      return false;
   }

   switch(result.retcode)
   {
      case TRADE_RETCODE_DONE:
         return true;
      case TRADE_RETCODE_REQUOTE:
      case TRADE_RETCODE_PRICE_CHANGED:
      case TRADE_RETCODE_OFF_QUOTES:
      case TRADE_RETCODE_TIMEOUT:
      case TRADE_RETCODE_CONNECTION:
      case TRADE_RETCODE_BROKER_BUSY:
         PrintFormat("Broker returned transient execution issue for %s: retcode=%d comment=%s",
                     symbol, result.retcode, result.comment);
         return false;
      case TRADE_RETCODE_INVALID_STOPS:
         PrintFormat("Invalid stop levels for %s: retcode=%d comment=%s",
                     symbol, result.retcode, result.comment);
         return false;
      default:
         PrintFormat("Order rejected for %s: retcode=%d comment=%s",
                     symbol, result.retcode, result.comment);
         return false;
   }
}

#property copyright "Aegis Quant"
#property version   "2.00"
#property strict

input string InpSymbol = "";
input ENUM_TIMEFRAMES InpTriggerTF = PERIOD_H1;
input ENUM_TIMEFRAMES InpBiasTF = PERIOD_H4;
input int InpFastEma = 50;
input int InpSlowEma = 200;
input int InpRsiPeriod = 14;
input int InpAtrPeriod = 14;
input int InpBarsToLoad = 250;
input double InpRiskPerTradePct = 1.0;
input double InpMaxDailyDrawdownPct = 3.0;
input double InpMaxSpreadPoints = 30.0;
input double InpAtrStopMult = 1.5;
input double InpAtrTpMult = 3.0;
input double InpAtrTrailMult = 1.25;
input double InpBreakevenR = 1.0;
input int InpDeviationPoints = 20;
input int InpMaxExecutionRetries = 2;
input ulong InpMagicNumber = 990011;
input int InpMaxConcurrentPositions = 3;
input double InpMaxLot = 50.0;
input bool InpAllowBuy = true;
input bool InpAllowSell = true;
input bool InpUseAsyncExecution = true;
input bool InpUseNewsBlackout = true;
input bool InpUseEconomicCalendar = true;
input int InpNewsBlackoutMinutes = 30;
input datetime InpNextNewsTimestamp = 0;
input string InpNewsCurrency = "";

string g_symbol;
datetime g_lastBar = 0;
datetime g_day = 0;
double g_dayStartEquity = 0.0;
ulong g_pendingRequest = 0;
int g_fastTrigger = INVALID_HANDLE;
int g_slowTrigger = INVALID_HANDLE;
int g_fastBias = INVALID_HANDLE;
int g_slowBias = INVALID_HANDLE;
int g_rsi = INVALID_HANDLE;
int g_atr = INVALID_HANDLE;

void Log(const string message) { PrintFormat("[AegisQuant] %s", message); }

int OnInit()
{
   g_symbol = StringLen(InpSymbol) > 0 ? InpSymbol : _Symbol;
   if(!SymbolSelect(g_symbol, true) || !IsTradeable()) return INIT_FAILED;
   g_fastTrigger = iMA(g_symbol, InpTriggerTF, InpFastEma, 0, MODE_EMA, PRICE_CLOSE);
   g_slowTrigger = iMA(g_symbol, InpTriggerTF, InpSlowEma, 0, MODE_EMA, PRICE_CLOSE);
   g_fastBias = iMA(g_symbol, InpBiasTF, InpFastEma, 0, MODE_EMA, PRICE_CLOSE);
   g_slowBias = iMA(g_symbol, InpBiasTF, InpSlowEma, 0, MODE_EMA, PRICE_CLOSE);
   g_rsi = iRSI(g_symbol, InpTriggerTF, InpRsiPeriod, PRICE_CLOSE);
   g_atr = iATR(g_symbol, InpTriggerTF, InpAtrPeriod);
   if(g_fastTrigger == INVALID_HANDLE || g_slowTrigger == INVALID_HANDLE ||
      g_fastBias == INVALID_HANDLE || g_slowBias == INVALID_HANDLE ||
      g_rsi == INVALID_HANDLE || g_atr == INVALID_HANDLE) return INIT_FAILED;
   ResetDailyBaseline();
   Log(StringFormat("initialized symbol=%s async=%s", g_symbol, InpUseAsyncExecution ? "true" : "false"));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_fastTrigger != INVALID_HANDLE) IndicatorRelease(g_fastTrigger);
   if(g_slowTrigger != INVALID_HANDLE) IndicatorRelease(g_slowTrigger);
   if(g_fastBias != INVALID_HANDLE) IndicatorRelease(g_fastBias);
   if(g_slowBias != INVALID_HANDLE) IndicatorRelease(g_slowBias);
   if(g_rsi != INVALID_HANDLE) IndicatorRelease(g_rsi);
   if(g_atr != INVALID_HANDLE) IndicatorRelease(g_atr);
}

void OnTick()
{
   ResetDailyBaseline();
   ManagePositions();
   if(!IsNewClosedBar() || !IsTradeable() || IsRiskBlocked() || IsNewsBlackout()) return;
   EvaluateAndTrade();
}

void OnTradeTransaction(const MqlTradeTransaction &transaction, const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(transaction.request_id != g_pendingRequest && result.request_id != g_pendingRequest) return;
   if(transaction.type == TRADE_TRANSACTION_DEAL_ADD)
      Log(StringFormat("async fill deal=%I64u price=%s volume=%s", transaction.deal,
                       DoubleToString(transaction.price, _Digits), DoubleToString(transaction.volume, 2)));
   if(result.retcode != 0 && result.retcode != TRADE_RETCODE_PLACED)
      Log(StringFormat("async result retcode=%u comment=%s", result.retcode, result.comment));
   if(transaction.type == TRADE_TRANSACTION_REQUEST) g_pendingRequest = 0;
}

bool IsTradeable()
{
   return (int)SymbolInfoInteger(g_symbol, SYMBOL_TRADE_MODE) == SYMBOL_TRADE_MODE_FULL &&
          SymbolInfoDouble(g_symbol, SYMBOL_BID) > 0.0 && SymbolInfoDouble(g_symbol, SYMBOL_ASK) > 0.0;
}

void ResetDailyBaseline()
{
   datetime today = StringToTime(TimeToString(TimeCurrent(), TIME_DATE));
   if(today != g_day || g_dayStartEquity <= 0.0)
   {
      g_day = today;
      g_dayStartEquity = AccountInfoDouble(ACCOUNT_EQUITY);
   }
}

bool IsRiskBlocked()
{
   if(g_dayStartEquity <= 0.0 || InpMaxDailyDrawdownPct <= 0.0) return false;
   double lossPct = 100.0 * (g_dayStartEquity - AccountInfoDouble(ACCOUNT_EQUITY)) / g_dayStartEquity;
   if(lossPct >= InpMaxDailyDrawdownPct)
   {
      Log(StringFormat("daily drawdown guard active loss=%.2f%%", lossPct));
      return true;
   }
   return false;
}

bool IsNewsBlackout()
{
   if(!InpUseNewsBlackout) return false;
   datetime now = TimeCurrent();
   if(InpNextNewsTimestamp > 0 && now >= InpNextNewsTimestamp - InpNewsBlackoutMinutes * 60 &&
      now <= InpNextNewsTimestamp + InpNewsBlackoutMinutes * 60) return true;
   if(!InpUseEconomicCalendar) return false;
   MqlCalendarValue values[];
   int count = CalendarValueHistory(values, now - InpNewsBlackoutMinutes * 60,
                                    now + InpNewsBlackoutMinutes * 60, NULL, InpNewsCurrency);
   for(int i = 0; i < count; i++)
   {
      MqlCalendarEvent event;
      if(CalendarEventById(values[i].event_id, event) && event.importance == CALENDAR_IMPORTANCE_HIGH) return true;
   }
   return false;
}

bool IsNewClosedBar()
{
   datetime bar = (datetime)SeriesInfoInteger(g_symbol, InpTriggerTF, SERIES_LASTBAR_DATE);
   if(bar <= 0 || bar <= g_lastBar) return false;
   g_lastBar = bar;
   return true;
}

bool ReadValue(const int handle, const int shift, double &value)
{
   if(handle == INVALID_HANDLE || BarsCalculated(handle) < InpBarsToLoad) return false;
   double buffer[1];
   if(CopyBuffer(handle, 0, shift, 1, buffer) != 1 || !MathIsValidNumber(buffer[0])) return false;
   value = buffer[0];
   return true;
}

int CountPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == g_symbol &&
         (ulong)PositionGetInteger(POSITION_MAGIC) == InpMagicNumber) count++;
   }
   return count;
}

void EvaluateAndTrade()
{
   if(CountPositions() >= InpMaxConcurrentPositions) return;
   double fastT, slowT, fastB, slowB, rsi, atr, previousRsi;
   if(!ReadValue(g_fastTrigger, 1, fastT) || !ReadValue(g_slowTrigger, 1, slowT) ||
      !ReadValue(g_fastBias, 1, fastB) || !ReadValue(g_slowBias, 1, slowB) ||
      !ReadValue(g_rsi, 1, rsi) || !ReadValue(g_rsi, 2, previousRsi) ||
      !ReadValue(g_atr, 1, atr) || atr <= 0.0) return;
   int direction = 0;
   if(InpAllowBuy && fastB > slowB && fastT > slowT && rsi >= 52.0 && rsi < 70.0 && rsi > previousRsi) direction = 1;
   if(InpAllowSell && fastB < slowB && fastT < slowT && rsi <= 48.0 && rsi > 30.0 && rsi < previousRsi) direction = -1;
   Log(StringFormat("signal trend=%s rsi=%.2f atr=%s direction=%d", fastT >= slowT ? "up" : "down",
                    rsi, DoubleToString(atr, _Digits), direction));
   if(direction != 0) SubmitEntry(direction, atr);
}

double NormalizePrice(const double price) { return NormalizeDouble(price, (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS)); }

double NormalizeVolume(double volume)
{
   double step = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_STEP);
   double minimum = SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_MIN);
   double maximum = MathMin(SymbolInfoDouble(g_symbol, SYMBOL_VOLUME_MAX), InpMaxLot);
   if(step <= 0.0 || maximum < minimum) return 0.0;
   volume = MathFloor(volume / step) * step;
   if(volume < minimum) return 0.0;
   return MathMin(volume, maximum);
}

double CalculateVolume(const double stopDistance)
{
   double tickSize = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(stopDistance <= 0.0 || tickSize <= 0.0 || tickValue <= 0.0 || equity <= 0.0) return 0.0;
   return NormalizeVolume((equity * InpRiskPerTradePct / 100.0) / ((stopDistance / tickSize) * tickValue));
}

int FillingMode()
{
   int flags = (int)SymbolInfoInteger(g_symbol, SYMBOL_FILLING_MODE);
   if((flags & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
   if((flags & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

bool IsTransientRetcode(const uint retcode)
{
   return retcode == TRADE_RETCODE_REQUOTE || retcode == TRADE_RETCODE_PRICE_CHANGED ||
          retcode == TRADE_RETCODE_OFF_QUOTES || retcode == TRADE_RETCODE_TIMEOUT ||
          retcode == TRADE_RETCODE_CONNECTION || retcode == TRADE_RETCODE_BROKER_BUSY ||
          retcode == TRADE_RETCODE_TOO_MANY_REQUESTS;
}

void SubmitEntry(const int direction, const double atr)
{
   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   double point = SymbolInfoDouble(g_symbol, SYMBOL_POINT);
   if(point <= 0.0 || (ask - bid) / point > InpMaxSpreadPoints) return;
   double entry = direction > 0 ? ask : bid;
   double stopDistance = MathMax(atr * InpAtrStopMult,
                                 (double)SymbolInfoInteger(g_symbol, SYMBOL_TRADE_STOPS_LEVEL) * point);
   double targetDistance = MathMax(atr * InpAtrTpMult, stopDistance);
   double sl = direction > 0 ? entry - stopDistance : entry + stopDistance;
   double tp = direction > 0 ? entry + targetDistance : entry - targetDistance;
   sl = NormalizePrice(sl); tp = NormalizePrice(tp);
   double volume = CalculateVolume(stopDistance);
   if(volume <= 0.0) return;
   MqlTradeRequest request = {};
   MqlTradeResult result = {};
   request.action = TRADE_ACTION_DEAL;
   request.magic = InpMagicNumber;
   request.symbol = g_symbol;
   request.volume = volume;
   request.type = direction > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   request.price = entry;
   request.sl = sl;
   request.tp = tp;
   request.deviation = InpDeviationPoints;
   request.type_filling = FillingMode();
   request.type_time = ORDER_TIME_GTC;
   request.comment = "AegisConfluence";
   MqlTradeCheckResult check = {};
   if(!InpUseAsyncExecution && OrderCheck(request, check) == false)
   {
      Log(StringFormat("order preflight rejected retcode=%u comment=%s", check.retcode, check.comment));
      return;
   }
   bool sent = false;
   int attempts = InpUseAsyncExecution ? 1 : MathMax(1, InpMaxExecutionRetries + 1);
   for(int attempt = 0; attempt < attempts; attempt++)
   {
      sent = InpUseAsyncExecution ? OrderSendAsync(request, result) : OrderSend(request, result);
      if(sent || !IsTransientRetcode(result.retcode)) break;
      Log(StringFormat("transient execution failure attempt=%d retcode=%u", attempt + 1, result.retcode));
   }
   Log(StringFormat("entry %s sent=%s retcode=%u volume=%s comment=%s", direction > 0 ? "BUY" : "SELL",
                    sent ? "true" : "false", result.retcode, DoubleToString(volume, 2), result.comment));
   if(sent && InpUseAsyncExecution && result.request_id > 0) g_pendingRequest = result.request_id;
}

void ManagePositions()
{
   double atr;
   if(!ReadValue(g_atr, 1, atr) || atr <= 0.0) return;
   double bid = SymbolInfoDouble(g_symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(g_symbol, SYMBOL_ASK);
   double point = SymbolInfoDouble(g_symbol, SYMBOL_POINT);
   double minimumDistance = (double)SymbolInfoInteger(g_symbol, SYMBOL_TRADE_STOPS_LEVEL) * point;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || PositionGetString(POSITION_SYMBOL) != g_symbol ||
         (ulong)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      long type = PositionGetInteger(POSITION_TYPE);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double oldSl = PositionGetDouble(POSITION_SL);
      double tp = PositionGetDouble(POSITION_TP);
      double price = type == POSITION_TYPE_BUY ? bid : ask;
      double risk = MathAbs(open - oldSl);
      if(risk <= point) continue;
      double candidate = type == POSITION_TYPE_BUY ? price - atr * InpAtrTrailMult : price + atr * InpAtrTrailMult;
      if(type == POSITION_TYPE_BUY && price - open >= risk * InpBreakevenR) candidate = MathMax(candidate, open);
      if(type == POSITION_TYPE_SELL && open - price >= risk * InpBreakevenR) candidate = MathMin(candidate, open);
      candidate = NormalizePrice(candidate);
      bool improves = type == POSITION_TYPE_BUY ? candidate > oldSl + point : candidate < oldSl - point;
      bool valid = type == POSITION_TYPE_BUY ? price - candidate >= minimumDistance : candidate - price >= minimumDistance;
      if(improves && valid) ModifyPosition(ticket, candidate, tp);
   }
}

void ModifyPosition(const ulong ticket, const double sl, const double tp)
{
   MqlTradeRequest request = {};
   MqlTradeResult result = {};
   request.action = TRADE_ACTION_SLTP;
   request.position = ticket;
   request.symbol = g_symbol;
   request.magic = InpMagicNumber;
   request.sl = sl;
   request.tp = tp;
   if(!OrderSend(request, result) || result.retcode != TRADE_RETCODE_DONE)
      Log(StringFormat("stop update failed ticket=%I64u retcode=%u comment=%s", ticket, result.retcode, result.comment));
}

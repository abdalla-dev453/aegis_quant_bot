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
input double InpMaxWeeklyDrawdownPct = 6.0;
input double InpMaxPeakDrawdownPct = 8.0;
input double InpMaxAggregateRiskPct = 3.0;
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
input bool InpUseAsyncExecution = false;
input long InpExpectedLogin = 0;
input string InpExpectedServer = "";
input ENUM_ACCOUNT_MARGIN_MODE InpExpectedMarginMode = ACCOUNT_MARGIN_MODE_RETAIL_HEDGING;
input bool InpAllowRealAccount = false;
input bool InpUseNewsBlackout = true;
input bool InpUseEconomicCalendar = true;
input int InpNewsBlackoutMinutes = 30;
input datetime InpNextNewsTimestamp = 0;
input string InpNewsCurrency = "";

string g_symbol;
datetime g_lastBar = 0;
datetime g_day = 0;
double g_dayStartEquity = 0.0;
datetime g_week = 0;
double g_weekStartEquity = 0.0;
double g_peakEquity = 0.0;
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
   long login = AccountInfoInteger(ACCOUNT_LOGIN);
   string server = AccountInfoString(ACCOUNT_SERVER);
   long tradeMode = AccountInfoInteger(ACCOUNT_TRADE_MODE);
   long marginMode = AccountInfoInteger(ACCOUNT_MARGIN_MODE);
   if(InpExpectedLogin <= 0 || StringLen(InpExpectedServer) == 0 ||
      login != InpExpectedLogin || server != InpExpectedServer ||
      marginMode != InpExpectedMarginMode)
   {
      Log("initialization blocked: expected login, server, and account margin mode must match");
      return INIT_FAILED;
   }
   if(tradeMode != ACCOUNT_TRADE_MODE_DEMO &&
      (tradeMode != ACCOUNT_TRADE_MODE_REAL || !InpAllowRealAccount))
   {
      Log("initialization blocked: real account execution is disabled by input");
      return INIT_FAILED;
   }
   if(InpRiskPerTradePct <= 0.0 || InpRiskPerTradePct > 100.0 ||
      InpMaxAggregateRiskPct <= 0.0 || InpMaxAggregateRiskPct > 100.0 ||
      InpMaxDailyDrawdownPct <= 0.0 || InpMaxDailyDrawdownPct > 100.0 ||
      InpMaxWeeklyDrawdownPct <= 0.0 || InpMaxWeeklyDrawdownPct > 100.0 ||
      InpMaxPeakDrawdownPct <= 0.0 || InpMaxPeakDrawdownPct > 100.0 ||
      InpMaxConcurrentPositions < 1 || InpUseAsyncExecution)
   {
      Log("initialization blocked: invalid risk inputs or async execution enabled without reconciliation support");
      return INIT_PARAMETERS_INCORRECT;
   }
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

string RiskStateKey(const string suffix)
{
   return StringFormat("AQ.%I64d.%I64u.%s", AccountInfoInteger(ACCOUNT_LOGIN),
                       InpMagicNumber, suffix);
}

bool PersistGlobal(const string key, const double value)
{
   if(GlobalVariableSet(key, value) == 0) return false;
   GlobalVariablesFlush();
   return true;
}

string PositionRiskKey(const ulong identifier)
{
   return StringFormat("AQ.%I64d.%I64u.R.%I64u", AccountInfoInteger(ACCOUNT_LOGIN),
                       InpMagicNumber, identifier);
}

void PersistPositionRisk(const ulong deal, const double riskDistance)
{
   if(deal == 0 || riskDistance <= 0.0 || !HistoryDealSelect(deal)) return;
   ulong positionId = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
   if(positionId > 0 && PersistGlobal(PositionRiskKey(positionId), riskDistance))
      Log(StringFormat("original risk persisted position=%I64u distance=%s", positionId,
                       DoubleToString(riskDistance, _Digits)));
}

bool RefreshExtendedRiskState()
{
   datetime now = TimeCurrent();
   datetime today = StringToTime(TimeToString(now, TIME_DATE));
   MqlDateTime parts;
   TimeToStruct(now, parts);
   int daysFromMonday = (parts.day_of_week + 6) % 7;
   datetime monday = StringToTime(TimeToString(today - daysFromMonday * 86400, TIME_DATE));
   string weekKey = RiskStateKey("WEEK");
   string weekEquityKey = RiskStateKey("WEEK_EQ");
   string weekHaltKey = RiskStateKey("WEEK_HALT");
   string peakKey = RiskStateKey("PEAK_EQ");
   string peakHaltKey = RiskStateKey("PEAK_HALT");
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0) return false;

   if(!GlobalVariableCheck(weekKey) || !GlobalVariableCheck(weekEquityKey) ||
      (datetime)GlobalVariableGet(weekKey) != monday)
   {
      if(!PersistGlobal(weekKey, (double)monday) || !PersistGlobal(weekEquityKey, equity) ||
         !PersistGlobal(weekHaltKey, 0.0)) return false;
   }
   if(!GlobalVariableCheck(weekHaltKey) && !PersistGlobal(weekHaltKey, 0.0)) return false;
   g_week = monday;
   g_weekStartEquity = GlobalVariableGet(weekEquityKey);

   if(!GlobalVariableCheck(peakKey))
   {
      if(!PersistGlobal(peakKey, equity)) return false;
   }
   if(!GlobalVariableCheck(peakHaltKey) && !PersistGlobal(peakHaltKey, 0.0)) return false;
   g_peakEquity = GlobalVariableGet(peakKey);
   if(equity > g_peakEquity)
   {
      if(!PersistGlobal(peakKey, equity)) return false;
      g_peakEquity = equity;
   }
   return g_weekStartEquity > 0.0 && g_peakEquity > 0.0;
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
      string dateKey = RiskStateKey("DAY");
      string equityKey = RiskStateKey("EQUITY");
      string haltKey = RiskStateKey("HALT");
      if(GlobalVariableCheck(dateKey) && GlobalVariableCheck(equityKey) &&
         (datetime)GlobalVariableGet(dateKey) == today)
      {
         g_day = today;
         g_dayStartEquity = GlobalVariableGet(equityKey);
         if(!GlobalVariableCheck(haltKey) && GlobalVariableSet(haltKey, 0.0) == 0)
         {
            g_day = 0;
            g_dayStartEquity = 0.0;
            Log("daily halt state could not be initialized; entries will remain blocked");
            return;
         }
      }
      else
      {
         double equity = AccountInfoDouble(ACCOUNT_EQUITY);
         if(equity <= 0.0 || GlobalVariableSet(dateKey, (double)today) == 0 ||
            GlobalVariableSet(equityKey, equity) == 0 || GlobalVariableSet(haltKey, 0.0) == 0)
         {
            g_day = 0;
            g_dayStartEquity = 0.0;
            Log("daily risk state could not be persisted; entries will remain blocked");
            return;
         }
         GlobalVariablesFlush();
         g_day = today;
         g_dayStartEquity = equity;
      }
   }
}

bool IsRiskBlocked()
{
   string haltKey = RiskStateKey("HALT");
   string killKey = RiskStateKey("KILL");
   if(GlobalVariableCheck(killKey) && GlobalVariableGet(killKey) >= 1.0)
   {
      Log("independent terminal kill switch is active; set the account/magic KILL global variable to 0 only after reconciliation");
      return true;
   }
   if(!RefreshExtendedRiskState())
   {
      Log("weekly/peak risk state unavailable; entry blocked");
      return true;
   }
   if(!GlobalVariableCheck(haltKey) || GlobalVariableGet(haltKey) >= 1.0) return true;
   if(g_dayStartEquity <= 0.0 || InpMaxDailyDrawdownPct <= 0.0) return true;
   double lossPct = 100.0 * (g_dayStartEquity - AccountInfoDouble(ACCOUNT_EQUITY)) / g_dayStartEquity;
   if(lossPct >= InpMaxDailyDrawdownPct)
   {
      GlobalVariableSet(haltKey, 1.0);
      GlobalVariablesFlush();
      Log(StringFormat("daily drawdown guard active loss=%.2f%%", lossPct));
      return true;
   }
   double weeklyLossPct = 100.0 * (g_weekStartEquity - AccountInfoDouble(ACCOUNT_EQUITY)) / g_weekStartEquity;
   string weekHaltKey = RiskStateKey("WEEK_HALT");
   if(GlobalVariableGet(weekHaltKey) >= 1.0 || weeklyLossPct >= InpMaxWeeklyDrawdownPct)
   {
      PersistGlobal(weekHaltKey, 1.0);
      Log(StringFormat("weekly drawdown guard active loss=%.2f%%", weeklyLossPct));
      return true;
   }
   double peakLossPct = 100.0 * (g_peakEquity - AccountInfoDouble(ACCOUNT_EQUITY)) / g_peakEquity;
   string peakHaltKey = RiskStateKey("PEAK_HALT");
   if(GlobalVariableGet(peakHaltKey) >= 1.0 || peakLossPct >= InpMaxPeakDrawdownPct)
   {
      PersistGlobal(peakHaltKey, 1.0);
      Log(StringFormat("peak drawdown guard active loss=%.2f%%", peakLossPct));
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
   if(count < 0)
   {
      Log("calendar lookup failed; entry blocked closed until calendar is available");
      return true;
   }
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

bool ExceedsAggregateRisk(const double proposedRisk)
{
   double totalRisk = proposedRisk;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || (ulong)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      string symbol = PositionGetString(POSITION_SYMBOL);
      double open = PositionGetDouble(POSITION_PRICE_OPEN);
      double stop = PositionGetDouble(POSITION_SL);
      double volume = PositionGetDouble(POSITION_VOLUME);
      double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
      double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
      if(stop <= 0.0 || tickSize <= 0.0 || tickValue <= 0.0 || volume <= 0.0)
      {
         Log(StringFormat("aggregate risk unknown for ticket=%I64u; entry blocked", ticket));
         return true;
      }
      totalRisk += MathAbs(open - stop) / tickSize * tickValue * volume;
   }
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0 || InpMaxAggregateRiskPct <= 0.0) return true;
   double maxRisk = equity * InpMaxAggregateRiskPct / 100.0;
   if(totalRisk > maxRisk)
   {
      Log(StringFormat("aggregate risk cap: current+proposed=%.2f limit=%.2f", totalRisk, maxRisk));
      return true;
   }
   return false;
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

double NormalizePrice(const double price, const bool roundUp)
{
   double tickSize = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tickSize <= 0.0) return 0.0;
   double units = price / tickSize;
   double snapped = roundUp ? MathCeil(units - 1e-10) : MathFloor(units + 1e-10);
   return NormalizeDouble(snapped * tickSize, (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS));
}

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
   sl = NormalizePrice(sl, direction < 0); tp = NormalizePrice(tp, direction > 0);
   double volume = CalculateVolume(stopDistance);
   if(volume <= 0.0) return;
   double tickSize = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(g_symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tickSize <= 0.0 || tickValue <= 0.0) return;
   double proposedRisk = (stopDistance / tickSize) * tickValue * volume;
   if(ExceedsAggregateRisk(proposedRisk)) return;
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
   if(sent && result.deal > 0 &&
      (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_DONE_PARTIAL))
      PersistPositionRisk(result.deal, stopDistance);
   if(result.retcode == TRADE_RETCODE_DONE_PARTIAL)
   {
      PersistGlobal(RiskStateKey("KILL"), 1.0);
      Log("partial fill received; independent kill latched pending broker reconciliation");
   }
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
      ulong identifier = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
      string riskKey = PositionRiskKey(identifier);
      double risk = MathAbs(open - oldSl);
      if(GlobalVariableCheck(riskKey)) risk = GlobalVariableGet(riskKey);
      else if(risk > point) PersistGlobal(riskKey, risk);
      if(risk <= point) continue;
      double candidate = type == POSITION_TYPE_BUY ? price - atr * InpAtrTrailMult : price + atr * InpAtrTrailMult;
      if(type == POSITION_TYPE_BUY && price - open >= risk * InpBreakevenR) candidate = MathMax(candidate, open);
      if(type == POSITION_TYPE_SELL && open - price >= risk * InpBreakevenR) candidate = MathMin(candidate, open);
      candidate = NormalizePrice(candidate, type == POSITION_TYPE_SELL);
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

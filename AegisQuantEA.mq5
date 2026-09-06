#property strict

input string   InpSymbol               = "EURUSD";
input ENUM_TIMEFRAME InpEntryTF         = PERIOD_H1;
input ENUM_TIMEFRAME InpBiasTF          = PERIOD_H4;
input int      InpFastEmaPeriod        = 50;
input int      InpSlowEmaPeriod        = 200;
input int      InpRsiPeriod            = 14;
input int      InpAtrPeriod            = 14;
input double   InpRiskPercent          = 1.5;
input double   InpAtrStopMultiplier    = 1.5;
input double   InpAtrTakeProfitMultiplier = 3.0;
input int      InpSlippagePoints       = 20;
input int      InpMagicNumber          = 990011;
input int      InpMaxPositions         = 3;
input bool     InpAllowLongs           = true;
input bool     InpAllowShorts          = false;
input double   InpMinLot               = 0.01;
input double   InpMaxLot               = 50.0;
input bool     InpUseNewsBlackout      = true;
input int      InpNewsBlackoutMinutes  = 30;
input datetime InpNextNewsTimestamp    = 0;

int g_fastEmaHandle = INVALID_HANDLE;
int g_slowEmaHandle = INVALID_HANDLE;
int g_rsiHandle = INVALID_HANDLE;
int g_atrHandle = INVALID_HANDLE;

string g_symbol = "";
ENUM_TIMEFRAME g_entryTF = PERIOD_H1;
ENUM_TIMEFRAME g_biasTF = PERIOD_H4;
datetime g_lastBarTime = 0;

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

bool IsTradeReady(string symbol)
{
   if(!SymbolSelect(symbol, true))
   {
      Print("[AegisQuant] Symbol selection failed: ", symbol);
      return false;
   }

   int tradeMode = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_MODE);
   if(tradeMode != SYMBOL_TRADE_MODE_FULL)
   {
      Print("[AegisQuant] Symbol is not fully tradeable: ", symbol, " tradeMode=", tradeMode);
      return false;
   }

   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0)
   {
      Print("[AegisQuant] Invalid bid/ask on symbol: ", symbol);
      return false;
   }

   return true;
}

bool ValidateStopsAndFreeze(string symbol, double entryPrice, double slPrice, double tpPrice)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int stopLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   int freezeLevel = (int)SymbolInfoInteger(symbol, SYMBOL_TRADE_FREEZE_LEVEL);

   if(stopLevel > 0)
   {
      if(MathAbs(entryPrice - slPrice) < stopLevel * point)
      {
         Print("[AegisQuant] Stop loss invalid for ", symbol, " | minDistance=", stopLevel * point);
         return false;
      }

      if(MathAbs(tpPrice - entryPrice) < stopLevel * point)
      {
         Print("[AegisQuant] Take profit invalid for ", symbol, " | minDistance=", stopLevel * point);
         return false;
      }
   }

   if(freezeLevel > 0)
   {
      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      if(MathAbs(ask - bid) > freezeLevel * point)
      {
         Print("[AegisQuant] Freeze level exceeded for ", symbol, " | spread=", MathAbs(ask-bid), " freezeLimit=", freezeLevel * point);
         return false;
      }
   }

   return true;
}

void HandleTradeResult(MqlTradeResult &result, string symbol, string direction)
{
   if(result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_DONE_PARTIAL)
   {
      Print("[AegisQuant] Order accepted | symbol=", symbol, " dir=", direction,
            " ticket=", result.order, " price=", result.price, " volume=", result.volume);
      return;
   }

   Print("[AegisQuant] Trade rejected | symbol=", symbol, " dir=", direction,
         " retcode=", result.retcode, " comment=", result.comment);

   switch(result.retcode)
   {
      case TRADE_RETCODE_REQUOTE:
      case TRADE_RETCODE_PRICE_CHANGED:
      case TRADE_RETCODE_OFF_QUOTES:
      case TRADE_RETCODE_TIMEOUT:
      case TRADE_RETCODE_CONNECTION:
      case TRADE_RETCODE_BROKER_BUSY:
         Print("[AegisQuant] Transient broker/server issue, skip and retry on next bar.");
         break;
      case TRADE_RETCODE_INVALID_STOPS:
         Print("[AegisQuant] Invalid stops relative to broker constraints.");
         break;
      case TRADE_RETCODE_INVALID_VOLUME:
         Print("[AegisQuant] Invalid lot size or volume step violation.");
         break;
      case TRADE_RETCODE_NO_MONEY:
         Print("[AegisQuant] No available margin or funds.");
         break;
      default:
         break;
   }
}

int GetFillingMode(string symbol)
{
   int mode = (int)SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);
   if(mode == SYMBOL_FILLING_IOC)
      return ORDER_FILLING_IOC;
   if(mode == SYMBOL_FILLING_FOK)
      return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
}

double GetDynamicRiskLotSize(string symbol, double stopDistancePrice)
{
   if(stopDistancePrice <= 0.0)
      return 0.0;

   double accountBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double riskAmount = MathMax(0.0, equity * (InpRiskPercent / 100.0));

   double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double volumeStep = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   double volumeMin = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double volumeMax = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);

   if(tickValue <= 0.0 || tickSize <= 0.0)
      return 0.0;

   double stopDistanceTicks = stopDistancePrice / MathMax(point, tickSize);
   double valuePerLot = stopDistanceTicks * tickValue;
   if(valuePerLot <= 0.0)
      return 0.0;

   double rawLots = riskAmount / valuePerLot;
   if(rawLots <= 0.0)
      return 0.0;

   double lots = MathFloor(rawLots / volumeStep) * volumeStep;
   if(lots < volumeMin)
      lots = volumeMin;
   if(lots > volumeMax)
      lots = volumeMax;
   if(lots > InpMaxLot)
      lots = InpMaxLot;
   if(lots < InpMinLot)
      lots = 0.0;

   double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double marginUsed = (lots * SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE) * SymbolInfoDouble(symbol, SYMBOL_ASK)) / MathMax((int)AccountInfoInteger(ACCOUNT_LEVERAGE), 1);
   if(freeMargin > 0.0 && marginUsed > freeMargin)
      return 0.0;

   Print("[AegisQuant] Dynamic lot sizing | symbol=", symbol, " equity=", equity, " risk=", riskAmount,
         " stopDistance=", stopDistancePrice, " rawLots=", rawLots, " lots=", lots);
   return lots;
}

bool GetIndicatorValue(int handle, int index, double &value)
{
   if(handle == INVALID_HANDLE)
      return false;

   double buf[];
   ArraySetAsSeries(buf, true);
   int copied = CopyBuffer(handle, 0, 0, 3, buf);
   if(copied <= 0)
      return false;

   value = buf[index];
   return true;
}

bool IsFreshEnough(string symbol, ENUM_TIMEFRAME tf)
{
   int neededBars = 200;
   int bars = Bars(symbol, tf);
   if(bars < neededBars)
   {
      Print("[AegisQuant] Not enough bars for ", symbol, " tf=", tf, " bars=", bars);
      return false;
   }

   if(g_fastEmaHandle != INVALID_HANDLE && BarsCalculated(g_fastEmaHandle) < neededBars)
      return false;
   if(g_slowEmaHandle != INVALID_HANDLE && BarsCalculated(g_slowEmaHandle) < neededBars)
      return false;
   if(g_rsiHandle != INVALID_HANDLE && BarsCalculated(g_rsiHandle) < neededBars)
      return false;
   if(g_atrHandle != INVALID_HANDLE && BarsCalculated(g_atrHandle) < neededBars)
      return false;

   MqlRates rates[];
   int copied = CopyRates(symbol, tf, 0, neededBars, rates);
   if(copied < neededBars)
   {
      Print("[AegisQuant] CopyRates incomplete for ", symbol, " tf=", tf, " copied=", copied);
      return false;
   }

   return true;
}

bool IsNewBarForSymbol()
{
   if(g_lastBarTime == 0)
   {
      g_lastBarTime = iTime(g_symbol, g_entryTF, 0);
      return true;
   }

   datetime currentBar = iTime(g_symbol, g_entryTF, 0);
   if(currentBar == g_lastBarTime)
      return false;

   g_lastBarTime = currentBar;
   return true;
}

double GetAtrValue(string symbol)
{
   double atr = 0.0;
   if(GetIndicatorValue(g_atrHandle, 0, atr))
      return atr;
   return 0.0;
}

bool EvaluateEntry(string symbol, int &tradeType)
{
   double fast = 0.0, slow = 0.0, rsi = 0.0;
   bool fastOk = GetIndicatorValue(g_fastEmaHandle, 0, fast);
   bool slowOk = GetIndicatorValue(g_slowEmaHandle, 0, slow);
   bool rsiOk = GetIndicatorValue(g_rsiHandle, 0, rsi);

   if(!fastOk || !slowOk || !rsiOk)
      return false;

   bool newsBlackout = IsNewsBlackoutActive();
   if(newsBlackout)
   {
      Print("[AegisQuant] News blackout active; skipping new entry.");
      return false;
   }

   bool rsiLongConfirm = rsi >= 52.0 && rsi < 70.0;
   bool rsiShortConfirm = rsi <= 48.0 && rsi > 30.0;

   if(fast > slow && rsiLongConfirm)
   {
      tradeType = OP_BUY;
      return true;
   }
   if(fast < slow && rsiShortConfirm)
   {
      tradeType = OP_SELL;
      return true;
   }

   return false;
}

bool SubmitMarketOrder(string symbol, int orderType, double atrValue)
{
   if(!IsTradeReady(symbol))
      return false;

   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0)
      return false;

   double entryPrice = (orderType == OP_BUY) ? ask : bid;
   double stopDistance = MathMax(atrValue * InpAtrStopMultiplier, SymbolInfoDouble(symbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(symbol, SYMBOL_POINT));

   double sl = 0.0, tp = 0.0;
   if(orderType == OP_BUY)
   {
      sl = entryPrice - stopDistance;
      tp = entryPrice + (atrValue * InpAtrTakeProfitMultiplier);
   }
   else
   {
      sl = entryPrice + stopDistance;
      tp = entryPrice - (atrValue * InpAtrTakeProfitMultiplier);
   }

   if(!ValidateStopsAndFreeze(symbol, entryPrice, sl, tp))
      return false;

   double lotSize = GetDynamicRiskLotSize(symbol, MathAbs(entryPrice - sl));
   if(lotSize <= 0.0)
   {
      Print("[AegisQuant] Order blocked because computed lot size is zero or invalid.");
      return false;
   }

   MqlTradeRequest request = {};
   MqlTradeResult result = {};

   request.action = TRADE_ACTION_DEAL;
   request.magic = InpMagicNumber;
   request.symbol = symbol;
   request.volume = lotSize;
   request.type = orderType;
   request.price = entryPrice;
   request.sl = sl;
   request.tp = tp;
   request.deviation = InpSlippagePoints;
   request.comment = "AegisQuantEA";
   request.type_filling = GetFillingMode(symbol);
   request.type_time = ORDER_TIME_GTC;

   bool sent = OrderSend(request, result);
   if(!sent)
   {
      Print("[AegisQuant] OrderSend returned false | symbol=", symbol, " retcode=", result.retcode, " comment=", result.comment);
      return false;
   }

   HandleTradeResult(result, symbol, (orderType == OP_BUY) ? "BUY" : "SELL");
   return (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_DONE_PARTIAL);
}

void EvaluateAndTrade()
{
   if(!IsFreshEnough(g_symbol, g_entryTF))
      return;

   int tradeType = -1;
   if(!EvaluateEntry(g_symbol, tradeType))
      return;

   if(tradeType == OP_BUY && !InpAllowLongs)
      return;
   if(tradeType == OP_SELL && !InpAllowShorts)
      return;

   int openPositions = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      CPositionInfo pos;
      if(!pos.SelectByTicket(ticket))
         continue;
      if(pos.Magic() == InpMagicNumber && pos.Symbol() == g_symbol)
         openPositions++;
   }

   if(openPositions >= InpMaxPositions)
   {
      Print("[AegisQuant] Max concurrent positions reached for ", g_symbol);
      return;
   }

   double atr = GetAtrValue(g_symbol);
   if(atr <= 0.0)
   {
      Print("[AegisQuant] Invalid ATR value, skip order for ", g_symbol);
      return;
   }

   SubmitMarketOrder(g_symbol, tradeType, atr);
}

int OnInit()
{
   g_symbol = InpSymbol;
   g_entryTF = InpEntryTF;
   g_biasTF = InpBiasTF;

   if(!IsTradeReady(g_symbol))
   {
      Print("[AegisQuant] Symbol trade readiness failed: ", g_symbol);
      return INIT_FAILED;
   }

   g_fastEmaHandle = iMA(g_symbol, g_entryTF, InpFastEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_slowEmaHandle = iMA(g_symbol, g_entryTF, InpSlowEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_rsiHandle = iRSI(g_symbol, g_entryTF, InpRsiPeriod, PRICE_CLOSE);
   g_atrHandle = iATR(g_symbol, g_entryTF, InpAtrPeriod);

   if(g_fastEmaHandle == INVALID_HANDLE || g_slowEmaHandle == INVALID_HANDLE || g_rsiHandle == INVALID_HANDLE || g_atrHandle == INVALID_HANDLE)
   {
      Print("[AegisQuant] Indicator handle creation failed.");
      return INIT_FAILED;
   }

   g_lastBarTime = 0;
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_fastEmaHandle != INVALID_HANDLE)
      IndicatorRelease(g_fastEmaHandle);
   if(g_slowEmaHandle != INVALID_HANDLE)
      IndicatorRelease(g_slowEmaHandle);
   if(g_rsiHandle != INVALID_HANDLE)
      IndicatorRelease(g_rsiHandle);
   if(g_atrHandle != INVALID_HANDLE)
      IndicatorRelease(g_atrHandle);

   g_fastEmaHandle = INVALID_HANDLE;
   g_slowEmaHandle = INVALID_HANDLE;
   g_rsiHandle = INVALID_HANDLE;
   g_atrHandle = INVALID_HANDLE;
}

void OnTick()
{
   if(!IsTradeReady(g_symbol))
      return;

   if(!IsNewBarForSymbol())
      return;

   EvaluateAndTrade();
}

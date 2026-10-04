import { useEffect, useRef, useState } from "react";
import * as feed from "./botFeed.js";

/**
 * useBotFeed
 * -----------------------------------------------------------------------
 * The one hook every page reads bot state from. Polls the bot's FastAPI
 * bridge (see botFeed.js) on intervals, with per-endpoint failure
 * tolerance: if one endpoint errors, the others keep updating and the
 * failed slice simply retains its last good value.
 */

// Empty but shape-correct initial states (mirrors server/models.py).
const EMPTY = {
  account: { netEquity: 0, balance: 0, todaysPnl: 0, freeMargin: 0, marginLevel: 0 },
  risk: { drawdownPct: 0, maxDrawdownCeilingPct: 5.0, dailyLossCeilingPct: 4.0, marginUtilizedPct: 0, openPositions: 0, tradesToday: 0, maxTradesPerDay: 0, peakDrawdownHalted: false, riskPerTradePct: null },
  performance: { winRatePct: 0, profitFactor: 0, totalTrades: 0, avgWin: 0, avgLoss: 0 },
  confluence: { composite: 0, label: "NEUTRAL", technical: 0, sentiment: 0, momentum: 0 },
  calendar: { autoHaltActive: false, autoHaltEtaSeconds: 0, nextEvent: null },
  control: { status: "RUNNING", entriesAllowed: true, managementAllowed: true, reason: null, source: "STARTUP", changedAt: "", revision: 0 },
  settings: { aiConfigured: false, tradingMode: "UNKNOWN" },
  proposals: [],
  orders: [],
  tradeAnalysis: { summary: { totalTrades: 0, netPnl: 0.0 }, recentTrades: [] },
};

const INTEGRALS = [
  ["account", feed.fetchAccount, 3000],
  ["risk", feed.fetchRisk, 3000],
  ["performance", feed.fetchPerformance, 10000],
  ["confluence", feed.fetchConfluence, 3000],
  ["calendar", feed.fetchCalendar, 5000],
  ["control", feed.fetchControl, 3000],
  ["settings", feed.fetchSettings, 15000],
  ["tradeAnalysis", feed.fetchTradeAnalysis, 10000],
];

export function useBotFeed() {
  const [account, setAccount] = useState(EMPTY.account);
  const [risk, setRisk] = useState(EMPTY.risk);
  const [performance, setPerformance] = useState(EMPTY.performance);
  const [confluence, setConfluence] = useState(EMPTY.confluence);
  const [calendar, setCalendar] = useState(EMPTY.calendar);
  const [control, setControl] = useState(EMPTY.control);
  const [settings, setSettings] = useState(EMPTY.settings);
  const [proposals, setProposals] = useState([]);
  const [orders, setOrders] = useState([]);
  const [tradeAnalysis, setTradeAnalysis] = useState(EMPTY.tradeAnalysis);
  const [positions, setPositions] = useState([]);
  const [priceSeries, setPriceSeries] = useState({ symbol: "", points: [] });
  const [equityCurve, setEquityCurve] = useState([]);
  const [logs, setLogs] = useState([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState({
    account: true,
    risk: true,
    performance: true,
    confluence: true,
    calendar: true,
    control: true,
    tradeAnalysis: true,
    positions: true,
    priceSeries: true,
    equityCurve: true,
    logs: true,
  });

  const connectedRef = useRef(false);
  const failuresRef = useRef(0);

  useEffect(() => {
    const timers = [];

    // Poll each snapshot endpoint on its own cadence.
    for (const [key, fn, ms] of INTEGRALS) {
      const setter = {
        account: setAccount,
        risk: setRisk,
        performance: setPerformance,
        confluence: setConfluence,
        calendar: setCalendar,
        control: setControl,
        settings: setSettings,
        tradeAnalysis: setTradeAnalysis,
      }[key];
      const tick = async () => {
        try {
          setter(await fn());
          setLoading((prev) => ({ ...prev, [key]: false }));
          failuresRef.current = 0;
          if (!connectedRef.current) {
            connectedRef.current = true;
            setConnected(true);
          }
        } catch {
          // Keep the feed connected through transient failures; disconnect after 3.
          failuresRef.current += 1;
          setLoading((prev) => ({ ...prev, [key]: false }));
          if (failuresRef.current >= 3 && connectedRef.current) {
            connectedRef.current = false;
            setConnected(false);
          }
        }
      };
      tick();
      timers.push(setInterval(tick, ms));
    }

    // Lists / series.
    const poll = async (fn, setter, loadingKey) => {
      try {
        setter(await fn());
        setLoading((prev) => ({ ...prev, [loadingKey]: false }));
      } catch {
        /* keep last good value */
        setLoading((prev) => ({ ...prev, [loadingKey]: false }));
      }
    };
    const proposalsTick = () => poll(feed.fetchProposals, setProposals, "proposals");
    const ordersTick = () => poll(feed.fetchOrders, setOrders, "orders");
    const positionsTick = () => poll(feed.fetchPositions, setPositions, "positions");
    const seriesTick = () => poll(feed.fetchPriceSeries, setPriceSeries, "priceSeries");
    const curveTick = () => poll(feed.fetchEquityCurve, setEquityCurve, "equityCurve");
    const logsTick = () => poll(feed.fetchLogs, setLogs, "logs");

    proposalsTick();
    ordersTick();
    positionsTick();
    seriesTick();
    curveTick();
    logsTick();
    timers.push(setInterval(proposalsTick, 5000));
    timers.push(setInterval(ordersTick, 5000));
    timers.push(setInterval(positionsTick, 3000));
    timers.push(setInterval(seriesTick, 8000));
    timers.push(setInterval(curveTick, 60000));
    timers.push(setInterval(logsTick, 4000));

    // Client-side 1s countdown for the auto-halt banner (server is authoritative).
    timers.push(
      setInterval(() => {
        setCalendar((prev) => {
          if (!prev.autoHaltActive) return prev;
          const nextEta = prev.autoHaltEtaSeconds - 1;
          return nextEta <= 0
            ? { ...prev, autoHaltActive: false, autoHaltEtaSeconds: 0 }
            : { ...prev, autoHaltEtaSeconds: nextEta };
        });
      }, 1000),
    );

    return () => timers.forEach(clearInterval);
  }, []);

  return { account, risk, performance, confluence, calendar, control, settings, proposals, orders, tradeAnalysis, positions, priceSeries, equityCurve, logs, connected, loading };
}
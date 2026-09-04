import { useEffect, useRef, useState } from "react";
import * as feed from "./botFeed.js";

/**
 * useBotFeed
 * -----------------------------------------------------------------------
 * The one hook every page reads bot state from. Everything below is
 * mock-driven on a timer to simulate a live connection. To connect to
 * the real bot, replace the body of this hook with fetch/WebSocket calls
 * against your backend bridge — keep the returned shape identical and
 * every consuming component keeps working unmodified.
 */
export function useBotFeed() {
  const [account, setAccount] = useState(feed.generateAccountState);
  const [risk, setRisk] = useState(feed.generateRiskState);
  const [performance, setPerformance] = useState(feed.generatePerformanceState);
  const [confluence, setConfluence] = useState(feed.generateConfluenceState);
  const [calendar, setCalendar] = useState(feed.generateCalendarState);
  const [positions, setPositions] = useState(feed.generatePositions);
  const [priceSeries, setPriceSeries] = useState(() => feed.generatePriceSeries());
  const [equityCurve, setEquityCurve] = useState(() => feed.generateEquityCurve());
  const [logs, setLogs] = useState(() =>
    Array.from({ length: 14 }, () => feed.generateLogEntry()).reverse()
  );

  const haltTicker = useRef(null);

  useEffect(() => {
    const positionsInterval = setInterval(() => setPositions(feed.generatePositions()), 3000);
    const logInterval = setInterval(() => {
      setLogs((prev) => [feed.generateLogEntry(), ...prev].slice(0, 40));
    }, 2200);
    const priceInterval = setInterval(() => setPriceSeries(feed.generatePriceSeries()), 8000);

    haltTicker.current = setInterval(() => {
      setCalendar((prev) => {
        if (!prev.autoHaltActive) return prev;
        const nextEta = prev.autoHaltEtaSeconds - 1;
        return nextEta <= 0
          ? { ...prev, autoHaltActive: false, autoHaltEtaSeconds: 0 }
          : { ...prev, autoHaltEtaSeconds: nextEta };
      });
    }, 1000);

    return () => {
      clearInterval(positionsInterval);
      clearInterval(logInterval);
      clearInterval(priceInterval);
      clearInterval(haltTicker.current);
    };
  }, []);

  return { account, risk, performance, confluence, calendar, positions, priceSeries, equityCurve, logs };
}
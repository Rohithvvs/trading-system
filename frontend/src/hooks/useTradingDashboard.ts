import { useState, useEffect } from "react";
import { fetchMarketEngineStatus, fetchPaperAccountSummary, loadTodayCandidates } from "../api";
import type { MarketEngineStatus, PaperTradingDashboardResponse, ScreenerConditionResult } from "../types";

export function useTradingDashboard() {
  const [engineStatus, setEngineStatus] = useState<MarketEngineStatus | null>(null);
  const [accountSummary, setAccountSummary] = useState<any | null>(null);
  const [recentScans, setRecentScans] = useState<ScreenerConditionResult[]>([]);
  const [isDisconnected, setIsDisconnected] = useState(false);
  const [isLiveDataActive, setIsLiveDataActive] = useState(false);

  useEffect(() => {
    let isMounted = true;

    async function pollData() {
      try {
        const [status, account, candidates] = await Promise.all([
          fetchMarketEngineStatus().catch(() => null),
          fetchPaperAccountSummary().catch(() => null),
          loadTodayCandidates().catch(() => [])
        ]);

        if (!isMounted) return;

        if (status && account) {
          setEngineStatus(status);
          setAccountSummary(account);
          if (candidates && candidates.length > 0) {
              setRecentScans(candidates.map((c: any) => ({
                  symbol: c.symbol,
                  screener_score: c.screener_score || 0,
                  technical_signal: c.technical_signal || "Neutral",
                  technical_score: c.technical_score || 0,
                  close: 0, ema_20: 0, sma_30: 0, sma_50: 0, sma_100: 0, sma_200: 0,
                  macd: 0, macd_signal: 0, supertrend: 0, volume: 0, previous_volume: 0,
                  conditions: {},
                  matched: c.matched
              })).filter(c => c.matched));
          }
          setIsDisconnected(false);
          
          // Data Health Evaluation
          // Check if engine is running and token/websocket is connected.
          const isLive = status.status === "running" && status.websocket_connected;
          setIsLiveDataActive(isLive);
        } else {
          setIsDisconnected(true);
          setIsLiveDataActive(false);
        }
      } catch (err) {
        if (!isMounted) return;
        setIsDisconnected(true);
        setIsLiveDataActive(false);
      }
    }

    pollData();
    const intervalId = setInterval(pollData, 10000);

    return () => {
      isMounted = false;
      clearInterval(intervalId);
    };
  }, []);

  return {
    engineStatus,
    accountSummary,
    recentScans,
    isDisconnected,
    isLiveDataActive,
  };
}

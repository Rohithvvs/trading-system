import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useNavigate, useSearchParams } from "react-router-dom";

import { fetchUniverses, loadLatestScan, runPresetScreener, saveScannerPreset } from "./api";
import { AllAnalyzedStocksTable } from "./components/AllAnalyzedStocksTable";
import { CandidateTable } from "./components/CandidateTable";
import { DashboardHeader } from "./components/DashboardHeader";
import { isMarketOpenForDisplay, checkCanPlaceBuyOrder, showMarketClosedAlert } from "./utils/tradingHours";
import { SummaryRow } from "./components/SummaryRow";
import type {
  CandidateRow,
  DashboardFilters,
  RankingItem,
  RecommendationPrefillRequest,
  ScanHistoryItem,
  ScreenerConditionResult,
  ScreenerResponse,
  SortKey,
  StockAnalysisResult,
} from "./types";

import { useAuth } from "./hooks/useAuth";
import { useTheme } from "./hooks/useTheme";
import { prefetchAppData } from "./utils/prefetchAppData";
import { ChartSkeleton, PanelSkeleton } from "./components/Skeleton";
import { AppShell } from "./layout/AppShell";
import { EmptyState, useToast } from "./design-system";
import { ScannerProgress } from "./components/ScannerProgress";
import { AdminRoute } from "./components/AdminRoute";
import FyersCallback from "./components/FyersCallback";

/** Code-split heavy modules — shell/nav paint first */
const PaperTradingPage = lazy(() =>
  import("./components/PaperTradingPage").then((m) => ({ default: m.PaperTradingPage })),
);
const UserProfilePage = lazy(() =>
  import("./components/profile/UserProfilePage").then((m) => ({ default: m.UserProfilePage })),
);
const SystemLogs = lazy(() =>
  import("./pages/SystemLogs").then((m) => ({ default: m.SystemLogs })),
);
const CentralCommand = lazy(() =>
  import("./components/CentralCommand").then((m) => ({ default: m.CentralCommand })),
);
const StockDetailPanel = lazy(() =>
  import("./components/StockDetailPanel").then((m) => ({ default: m.StockDetailPanel })),
);
const MarketsPage = lazy(() =>
  import("./pages/MarketsPage").then((m) => ({ default: m.MarketsPage })),
);
const WatchlistPage = lazy(() =>
  import("./pages/WatchlistPage").then((m) => ({ default: m.WatchlistPage })),
);
const PerformancePage = lazy(() =>
  import("./pages/PerformancePage").then((m) => ({ default: m.PerformancePage })),
);

function ViewFallback() {
  return (
    <div className="page-container" style={{ padding: 16 }} aria-busy="true">
      <PanelSkeleton title="Loading">
        <ChartSkeleton height={120} />
      </PanelSkeleton>
    </div>
  );
}

const DEFAULT_FILTERS: DashboardFilters = {
  signal: "ALL",
  search: "",
  scoreRange: [0, 100],
  sortBy: "rank",
  onlyHighConfidence: false,
};

export default function App() {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const toast = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const symbolParam = searchParams.get("symbol");

  const [timeframe, setTimeframe] = useState("1d");
  const [lookback, setLookback] = useState(180);
  const [topN, setTopN] = useState(20);
  const [selectedUniverse, setSelectedUniverse] = useState("NIFTY500");
  const [universes, setUniverses] = useState<{ name: string; symbols: string[]; count: number }[]>([]);
  const [savedScanName, setSavedScanName] = useState("");
  const [filters, setFilters] = useState<DashboardFilters>(DEFAULT_FILTERS);
  const [screenerResult, setScreenerResult] = useState<ScreenerResponse | null>(null);
  const [scanHistory, setScanHistory] = useState<ScanHistoryItem[]>(() => loadScanHistory());
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [detailViewOpen, setDetailViewOpen] = useState(false);
  const [paperTradingPrefill, setPaperTradingPrefill] = useState<RecommendationPrefillRequest | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAllAnalyzedStocks, setShowAllAnalyzedStocks] = useState(false);

  const [progressStage, setProgressStage] = useState("Initializing...");
  const [progressPercent, setProgressPercent] = useState(0);
  const [scanStartTime, setScanStartTime] = useState<number | null>(null);

  const universesMapped = useMemo(
    () => universes.map(({ name, count }) => ({ name, count })),
    [universes],
  );

  const handleSearchChange = useCallback(
    (value: string) => setFilters((current) => ({ ...current, search: value })),
    [],
  );

  const handleSelectSymbol = useCallback(
    (symbol: string) => {
      setSelectedSymbol(symbol);
      setDetailViewOpen(true);
      navigate(`/scanner?symbol=${encodeURIComponent(symbol)}`, { replace: true });
    },
    [navigate],
  );

  const handleDetailBack = useCallback(() => {
    setDetailViewOpen(false);
    navigate("/scanner", { replace: true });
  }, [navigate]);

  // Warm app cache after login
  useEffect(() => {
    if (user?.id) prefetchAppData();
  }, [user?.id]);

  useEffect(() => {
    function loadAndApply() {
      void loadLatestScan().then((saved) => {
        if (!saved) return;
        applyScanResult(saved, "restored");
      });
    }

    loadAndApply();

    const intervalId = setInterval(() => {
      const status = getMarketStatus();
      if (status === "Open") {
        console.info("[scanner] 30-min auto-polling new cached scan...");
        loadAndApply();
      }
    }, 30 * 60 * 1000);

    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    void fetchUniverses().then(setUniverses).catch((err) => console.warn("Failed to load universes", err));
  }, []);

  // Deep-link: /scanner?symbol=RELIANCE opens stock detail
  useEffect(() => {
    if (symbolParam) {
      setSelectedSymbol(symbolParam.toUpperCase());
      setDetailViewOpen(true);
    }
  }, [symbolParam]);

  const marketStatus = useMemo(() => getMarketStatus(), []);
  const analysisItems = screenerResult?.analysis?.items ?? [];
  const shortlistRows = useMemo(() => buildCandidateRows(screenerResult), [screenerResult]);

  const filteredRows = useMemo(() => {
    const searchTerm = filters.search.trim().toUpperCase();
    return shortlistRows
      .filter((row) => {
        if (filters.signal === "ALL") return true;
        const sig = (row.signal || "").toLowerCase().trim();
        if (filters.signal === "BUY") return sig === "buy" || sig === "bullish";
        if (filters.signal === "WATCH") return sig === "watch" || sig === "neutral" || sig === "sideways";
        if (filters.signal === "REJECT") return sig === "reject" || sig === "bearish" || sig === "sell";
        return true;
      })
      .filter((row) => row.score >= filters.scoreRange[0] && row.score <= filters.scoreRange[1])
      .filter((row) => (filters.onlyHighConfidence ? (row.confidence ?? 0) >= 0.7 : true))
      .filter((row) => (searchTerm ? row.symbol.includes(searchTerm) : true))
      .sort((left, right) => compareRows(left, right, filters.sortBy));
  }, [filters, shortlistRows]);

  const selectedRow = useMemo(() => {
    if (!filteredRows.length) return null;
    return filteredRows.find((row) => row.symbol === selectedSymbol) ?? filteredRows[0];
  }, [filteredRows, selectedSymbol]);

  const summaryMetrics = useMemo(() => {
    const favoritesCount = screenerResult?.shortlisted_symbols.length ?? 0;
    const buyCount = screenerResult?.buy_candidate_symbols.length ?? 0;
    const watchCount = screenerResult?.watch_candidate_symbols.length ?? 0;
    const rejectedCount = Math.max(favoritesCount - buyCount - watchCount, 0);

    return [
      { label: "Total scanned", value: screenerResult?.scanned_symbols ?? "--", helper: "Stocks checked in the universe." },
      { label: "Data valid", value: screenerResult?.data_valid_symbols?.length ?? "--", helper: "Names with enough clean OHLCV history." },
      { label: "Trend matched", value: screenerResult?.eligible_symbols?.length ?? "--", helper: "Names passing the broad trend gate.", tone: "positive" as const },
      { label: "Favorites", value: favoritesCount || "--", helper: "Top set moved into deeper analysis." },
      { label: "BUY ideas", value: buyCount || "--", helper: "Actionable swing ideas right now.", tone: "positive" as const },
      { label: "WATCH ideas", value: watchCount || "--", helper: "Promising names needing confirmation.", tone: "warning" as const },
      { label: "Rejected", value: rejectedCount || "--", helper: "Names that failed final recommendation.", tone: "negative" as const },
    ];
  }, [screenerResult]);

  const applyScanResult = useCallback((response: ScreenerResponse, _source: "fresh" | "restored") => {
    response.shortlisted_symbols = response.shortlisted_symbols || [];
    response.buy_candidate_symbols = response.buy_candidate_symbols || [];
    response.watch_candidate_symbols = response.watch_candidate_symbols || [];

    setScreenerResult(response);
    setScanHistory((current) => saveScanHistory(response, current));
    setSelectedSymbol(
      response.shortlisted_symbols[0] ?? response.buy_candidate_symbols[0] ?? response.watch_candidate_symbols[0] ?? null,
    );
    setDetailViewOpen(false);
  }, []);

  const handleRunScanner = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setProgressStage("Connecting data feed...");
    setProgressPercent(0);
    setScanStartTime(Date.now());

    try {
      const response = await runPresetScreener(
        "swing",
        {
          intraday: "5m",
          swing: timeframe,
          lookback_window: lookback,
        },
        selectedUniverse === "NIFTY500" ? [] : universes.find((item) => item.name === selectedUniverse)?.symbols ?? [],
        topN,
        (stage, progress) => {
          setProgressStage(stage);
          setProgressPercent(progress);
        },
      );

      applyScanResult(response, "fresh");
      toast.success("Scan complete", `${response.buy_candidate_symbols?.length ?? 0} BUY · ${response.watch_candidate_symbols?.length ?? 0} WATCH`);
    } catch (requestError: any) {
      console.error("[scanner] scanner request failed", requestError);
      const detail = requestError?.response?.data?.detail || requestError?.detail || null;

      let errorMessage = "Scanner failed. Please try again.";

      if (detail?.error_type === "FYERS_TOKEN_EXPIRED") {
        errorMessage = "Broker session expired — reconnect your broker and try again.";
      } else if (detail?.error_type === "FYERS_TOKEN_INVALID") {
        errorMessage = "Broker credentials invalid — check your connection settings.";
      } else if (detail?.error_type === "FYERS_RATE_LIMIT") {
        errorMessage = "Rate limit hit — wait about 60 seconds and try again.";
      } else if (detail?.error_type === "FYERS_API_ERROR") {
        errorMessage = `Broker error — ${detail.message}`;
      } else if (detail?.message) {
        errorMessage = detail.message;
      } else if (typeof requestError?.message === "string") {
        errorMessage = requestError.message;
      }

      setError(errorMessage);
      toast.error("Scan failed", errorMessage);
      setScanStartTime(null);
    } finally {
      setIsLoading(false);
      setScanStartTime(null);
    }
  }, [timeframe, lookback, selectedUniverse, universes, topN, toast, applyScanResult]);

  async function handleSaveCurrentScan() {
    const name = savedScanName.trim() || `${selectedUniverse} ${timeframe} scan`;
    try {
      await saveScannerPreset({
        name,
        mode: "swing",
        timeframe,
        lookback_window: lookback,
        top_n: topN,
        universe: selectedUniverse,
        symbols: selectedUniverse === "NIFTY500" ? [] : universes.find((item) => item.name === selectedUniverse)?.symbols ?? [],
        filters,
      });
      setSavedScanName("");
      toast.success("Scan saved", name);
    } catch (e: any) {
      toast.error("Could not save scan", e?.message);
    }
  }

  function handleExportCsv() {
    const rows = screenerResult?.all_analyzed_stocks?.length ? screenerResult.all_analyzed_stocks : screenerResult?.matches ?? [];
    if (!rows.length) {
      toast.info("Nothing to export yet");
      return;
    }
    const headers = ["symbol", "close", "screener_score", "technical_signal", "matched", "volume"];
    const csv = [headers.join(","), ...rows.map((row: any) => headers.map((key) => JSON.stringify(row[key] ?? "")).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `scan-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success("CSV exported");
  }

  function loadSavedScan(scan: any) {
    setSelectedUniverse(scan.universe ?? "NIFTY500");
    setTimeframe(scan.timeframe ?? "1d");
    setLookback(scan.lookback_window ?? 180);
    setTopN(scan.top_n ?? 20);
    navigate("/scanner");
  }

  const sendRowToPaperTrading = useCallback((row: CandidateRow, suggestedEntry?: number | null) => {
    const sig = (row as any).signal || (row as any).recommendation;
    if (sig === "BUY") {
      const check = checkCanPlaceBuyOrder();
      if (!check.allowed) {
        showMarketClosedAlert(check);
        return;
      }
    }
    const prefill = buildPaperTradingPrefill(row);
    setPaperTradingPrefill({
      ...prefill,
      suggested_entry: suggestedEntry ?? prefill.suggested_entry,
    });
    navigate("/paper");
  }, [navigate]);

  const scannerView =
    detailViewOpen && selectedRow ? (
      <main className="page-container detail-screen-layout">
        <Suspense fallback={<ViewFallback />}>
          <StockDetailPanel
            row={selectedRow}
            onBack={handleDetailBack}
            onSendToPaperTrading={sendRowToPaperTrading}
          />
        </Suspense>
      </main>
    ) : (
      <>
        <DashboardHeader
          isLoading={isLoading}
          lastScanAt={screenerResult?.last_scan_completed_at ?? screenerResult?.scanned_at ?? screenerResult?.analysis?.generated_at ?? null}
          marketStatus={marketStatus}
          search={filters.search}
          onSearchChange={handleSearchChange}
          onRunScanner={handleRunScanner}
          topN={topN}
          lookback={lookback}
          timeframe={timeframe}
          universe={selectedUniverse}
          universes={universesMapped}
          onTopNChange={setTopN}
          onLookbackChange={setLookback}
          onTimeframeChange={setTimeframe}
          onUniverseChange={setSelectedUniverse}
          theme={theme}
          onThemeToggle={toggleTheme}
        />

        <main className="page-container scanner-layout">
          <div className="scanner-center">
            <div className="scanner-status-bar">
              <span className={`ds-status-pill ds-status-pill--${marketStatus === "Open" ? "online" : "offline"}`}>
                <span className="ds-status-pill__dot" aria-hidden />
                Market {marketStatus === "Open" ? "open" : "closed"}
              </span>
              <span className={`ds-status-pill ds-status-pill--${screenerResult ? "online" : "idle"}`}>
                <span className="ds-status-pill__dot" aria-hidden />
                {isLoading ? "Scanning…" : screenerResult ? "Scan ready" : "Awaiting scan"}
              </span>
              <span className="ds-caption scanner-status-bar__meta">
                {selectedUniverse} · {timeframe}
                {screenerResult?.scanned_symbols != null ? ` · ${screenerResult.scanned_symbols} scanned` : ""}
              </span>
            </div>
            <SummaryRow metrics={summaryMetrics} />

            {screenerResult?.data_warning ? (
              <section className="panel warning-box">
                <strong>Data feed notice</strong>
                <p>{screenerResult.data_warning}</p>
              </section>
            ) : null}

            <div className="scanner-result-tabs" role="tablist" aria-label="Result views">
              <button
                type="button"
                role="tab"
                aria-selected={!showAllAnalyzedStocks}
                className={`button ${!showAllAnalyzedStocks ? "primary-button" : "ghost-button"}`}
                onClick={() => setShowAllAnalyzedStocks(false)}
              >
                Favorites ({screenerResult?.shortlisted_symbols.length ?? 0})
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={showAllAnalyzedStocks}
                className={`button ${showAllAnalyzedStocks ? "primary-button" : "ghost-button"}`}
                onClick={() => setShowAllAnalyzedStocks(true)}
              >
                Scan results ({screenerResult?.all_analyzed_stocks?.length ?? 0})
              </button>
            </div>

            {isLoading ? (
              <ScannerProgress
                stage={progressStage}
                progress={progressPercent}
                error={error}
                startTime={scanStartTime}
                onRetry={handleRunScanner}
              />
            ) : null}

            {error ? (
              <section className="panel error-state" role="alert">
                <h2 className="ds-title">Scan failed</h2>
                <p>{error}</p>
                <button type="button" className="button primary-button" onClick={handleRunScanner} style={{ marginTop: 12 }}>
                  Retry scan
                </button>
              </section>
            ) : null}

            {!isLoading && !error ? (
              showAllAnalyzedStocks ? (
                <AllAnalyzedStocksTable stocks={screenerResult?.all_analyzed_stocks ?? []} />
              ) : filteredRows.length ? (
                <CandidateTable
                  rows={filteredRows}
                  selectedSymbol={selectedRow?.symbol ?? null}
                  onSelect={handleSelectSymbol}
                  onBuy={sendRowToPaperTrading}
                />
              ) : screenerResult ? (
                <EmptyState
                  title="No matches for these filters"
                  description="Adjust signal, score range, or search to see more results."
                  primaryAction={{ label: "Modify filters", onClick: () => setFilters(DEFAULT_FILTERS), variant: "secondary" }}
                />
              ) : null
            ) : null}

            {!screenerResult && !isLoading && !error ? (
              <EmptyState
                title="Ready for the next scan"
                description="Scan the market, review favorites, and open a stock for execution-ready detail."
                primaryAction={{ label: "Run scanner", onClick: () => void handleRunScanner(), variant: "trade" }}
              />
            ) : null}

            {screenerResult ? (
              <section className="panel footer-note">
                <p>
                  <strong>{screenerResult.screener_name}</strong> is advisory only. You make the final trading decision.
                </p>
                <p>
                  Sample rows: {analysisItems.length} analyzed · {filteredRows.length} visible after filters.
                </p>
              </section>
            ) : null}
          </div>
        </main>
      </>
    );

  const paperDeskView = (
    <div className="page-container page-container--wide">
      <Suspense fallback={<ViewFallback />}>
        <PaperTradingPage
          recommendationPrefill={paperTradingPrefill}
          onPrefillConsumed={() => setPaperTradingPrefill(null)}
          scannerCandidates={shortlistRows}
          lastScanAt={screenerResult?.analysis?.generated_at ?? null}
          retailMode
        />
      </Suspense>
    </div>
  );

  const profileView = (
    <Suspense fallback={<ViewFallback />}>
      <UserProfilePage
        retailMode
        onNavigate={(view) => {
          if (view === "scanner") navigate("/scanner");
          else if (view === "paper-trading") navigate("/paper");
          else navigate("/markets");
        }}
      />
    </Suspense>
  );

  return (
    <AppShell>
      <Suspense fallback={<ViewFallback />}>
        <Routes>
          <Route path="/" element={<Navigate to="/scanner" replace />} />
          <Route path="/home" element={<Navigate to="/scanner" replace />} />
          <Route
            path="/markets"
            element={
              <Suspense fallback={<ViewFallback />}>
                <MarketsPage onLoadSavedScan={loadSavedScan} />
              </Suspense>
            }
          />
          <Route path="/scanner" element={scannerView} />
          <Route
            path="/watchlist"
            element={
              <Suspense fallback={<ViewFallback />}>
                <WatchlistPage />
              </Suspense>
            }
          />
          <Route path="/paper" element={paperDeskView} />
          <Route path="/paper/:section" element={paperDeskView} />
          <Route
            path="/performance"
            element={
              <Suspense fallback={<ViewFallback />}>
                <PerformancePage />
              </Suspense>
            }
          />
          <Route path="/profile" element={profileView} />
          <Route path="/logs" element={<Navigate to="/admin/logs" replace />} />
          <Route
            path="/admin/logs"
            element={
              <AdminRoute>
                <Suspense fallback={<ViewFallback />}>
                  <SystemLogs />
                </Suspense>
              </AdminRoute>
            }
          />
          <Route
            path="/admin/command"
            element={
              <AdminRoute>
                <Suspense fallback={<ViewFallback />}>
                  <CentralCommand />
                </Suspense>
              </AdminRoute>
            }
          />
          <Route path="/fyers/callback" element={<FyersCallback />} />
          <Route path="*" element={<Navigate to="/scanner" replace />} />
        </Routes>
      </Suspense>
    </AppShell>
  );
}

function buildPaperTradingPrefill(row: CandidateRow): RecommendationPrefillRequest {
  const plan =
    row.analysisItem?.recommendation.trade_plans.find((item) => item.mode === "swing") ??
    row.analysisItem?.recommendation.trade_plans[0];
  return {
    symbol: row.symbol,
    suggested_entry: plan ? (plan.entry_low + plan.entry_high) / 2 : row.entryLow,
    suggested_stop: plan?.stop_loss ?? row.stopLoss ?? null,
    suggested_targets: [plan?.target_1, plan?.target_2].filter((value): value is number => typeof value === "number"),
    recommendation_meta: {
      signal: row.signal,
      score: row.score,
      confidence: Math.round((row.confidence ?? 0) * 100) / 100,
    },
  };
}

function buildCandidateRows(screenerResult: ScreenerResponse | null): CandidateRow[] {
  if (!screenerResult) return [];

  const analysisBySymbol = new Map<string, StockAnalysisResult>();
  const matchBySymbol = new Map<string, ScreenerConditionResult>();
  const rankingBySymbol = new Map<string, RankingItem>();

  screenerResult.analysis?.items?.forEach((item) => {
    analysisBySymbol.set(item.symbol, item);
  });
  screenerResult.matches?.forEach((match) => {
    matchBySymbol.set(match.symbol, match);
  });
  screenerResult.analysis?.rankings?.rankings?.forEach((ranking) => {
    rankingBySymbol.set(ranking.symbol, ranking);
  });

  return screenerResult.shortlisted_symbols.map((symbol) => {
    const analysis = analysisBySymbol.get(symbol);
    const match = matchBySymbol.get(symbol);
    const ranking = rankingBySymbol.get(symbol);
    const plan =
      analysis?.recommendation.trade_plans.find((item) => item.mode === "swing") ??
      analysis?.recommendation.trade_plans[0];
    const technical = analysis?.technical.find((item) => item.mode === "swing") ?? analysis?.technical[0];

    let signal: CandidateRow["signal"] = "REJECT";
    if (screenerResult.buy_candidate_symbols.includes(symbol)) {
      signal = "BUY";
    } else if (screenerResult.watch_candidate_symbols.includes(symbol)) {
      signal = "WATCH";
    }

    return {
      rank: ranking?.rank ?? null,
      symbol,
      signal,
      score: analysis?.recommendation.score ?? match?.screener_score ?? 0,
      confidence: analysis?.recommendation.confidence ?? null,
      entryLow: plan?.entry_low ?? null,
      entryHigh: plan?.entry_high ?? null,
      stopLoss: plan?.stop_loss ?? null,
      target1: plan?.target_1 ?? null,
      target2: plan?.target_2 ?? null,
      riskReward: plan?.risk_reward_ratio ?? null,
      trend: formatTrend(technical, match),
      momentum: formatMomentum(technical, match),
      volume: formatVolume(technical, match),
      newsSentiment: analysis?.news_sentiment_label ?? "n/a",
      lastUpdated: screenerResult.analysis?.generated_at ?? null,
      tradeReadiness: analysis?.trade_readiness ?? (signal === "REJECT" ? "Avoid" : "Review manually"),
      recommendationSummary:
        analysis?.recommendation.summary ??
        (signal === "REJECT"
          ? "Rejected after the shortlist because the final recommendation layer did not confirm the setup."
          : "This stock passed the screener and is awaiting deeper analysis."),
      analysisItem: analysis,
      screenerMatch: match,
    };
  });
}

function loadScanHistory(): ScanHistoryItem[] {
  try {
    return JSON.parse(window.localStorage.getItem("scanHistory") ?? "[]") as ScanHistoryItem[];
  } catch {
    return [];
  }
}

function saveScanHistory(response: ScreenerResponse, current: ScanHistoryItem[]) {
  const shortlisted = response.shortlisted_symbols || [];
  const item: ScanHistoryItem = {
    id: `${response.analysis?.generated_at ?? new Date().toISOString()}-${shortlisted.join("-")}`,
    generated_at: response.analysis?.generated_at ?? new Date().toISOString(),
    screener_name: response.screener_name || "Unknown",
    scanned_symbols: response.scanned_symbols || 0,
    shortlisted_count: shortlisted.length,
    buy_symbols: response.buy_candidate_symbols || [],
    watch_symbols: response.watch_candidate_symbols || [],
    data_source: response.data_source || "unknown",
    data_warning: response.data_warning || null,
  };
  const next = [item, ...current.filter((entry) => entry.id !== item.id)].slice(0, 20);
  window.localStorage.setItem("scanHistory", JSON.stringify(next));
  return next;
}

function compareRows(left: CandidateRow, right: CandidateRow, sortBy: SortKey) {
  if (sortBy === "rank") return (left.rank ?? 999) - (right.rank ?? 999);
  if (sortBy === "confidence") return (right.confidence ?? -1) - (left.confidence ?? -1);
  if (sortBy === "riskReward") return (right.riskReward ?? -1) - (left.riskReward ?? -1);
  return right.score - left.score;
}

function formatTrend(
  technical: StockAnalysisResult["technical"][number] | undefined,
  match: ScreenerConditionResult | undefined,
) {
  if (technical?.indicators.higher_timeframe_trend) {
    return String(technical.indicators.higher_timeframe_trend);
  }
  if (match?.conditions.supertrend_positive && match.conditions.close_above_ema20) {
    return "uptrend";
  }
  return "mixed";
}

function formatMomentum(
  technical: StockAnalysisResult["technical"][number] | undefined,
  match: ScreenerConditionResult | undefined,
) {
  if (!technical && !match) return "n/a";
  const macdPositive = technical ? Boolean(technical.indicators.macd_positive) : Boolean(match?.conditions.macd_positive);
  const rsiSupportive = technical ? Boolean(technical.indicators.rsi_supportive) : true;
  return macdPositive && rsiSupportive ? "supported" : macdPositive ? "mixed" : "weak";
}

function formatVolume(
  technical: StockAnalysisResult["technical"][number] | undefined,
  match: ScreenerConditionResult | undefined,
) {
  if (technical) {
    const liquid = Boolean(technical.indicators.basic_liquidity_filter_pass);
    const expanding = Boolean(technical.indicators.volume_above_previous_day);
    return liquid && expanding ? "expanding" : liquid ? "adequate" : "thin";
  }
  if (!match) return "n/a";
  return match.conditions.volume_above_previous_day ? "expanding" : "adequate";
}

function getMarketStatus() {
  try {
    return isMarketOpenForDisplay();
  } catch {
    const now = new Date();
    const day = now.getDay();
    const minutes = now.getHours() * 60 + now.getMinutes();
    const open = 9 * 60 + 15;
    const close = 15 * 60 + 30;
    if (day === 0 || day === 6) return "Closed";
    return minutes >= open && minutes <= close ? "Open" : "Closed";
  }
}

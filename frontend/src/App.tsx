import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, Route, Routes, useNavigate, useSearchParams } from "react-router-dom";

import {
  cacheLatestScanFromScreenerResponse,
  fetchUniverses,
  invalidateLatestScanCaches,
  loadLatestScan,
  runPresetScreener,
  saveScannerPreset,
} from "./api";

const AllAnalyzedStocksTable = lazy(() =>
  import("./components/AllAnalyzedStocksTable").then((m) => ({ default: m.AllAnalyzedStocksTable })),
);
const CandidateTable = lazy(() =>
  import("./components/CandidateTable").then((m) => ({ default: m.CandidateTable })),
);
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
import { StatusCards } from "./components/StatusCards";
import { AdminRoute } from "./components/AdminRoute";
import FyersCallback from "./components/FyersCallback";
import { PaperOrderProvider } from "./contexts/PaperOrderContext";
import { navigateToPaperOrder } from "./utils/paperOrderNavigation";
import { FeaturePermissionsProvider } from "./contexts/FeaturePermissionsContext";
import { FeatureGuard } from "./components/FeatureGuard";
import { AccessDenied } from "./components/AccessDenied";

/** Code-split heavy modules — shell/nav paint first */
const PaperTradingPage = lazy(() =>
  import("./components/PaperTradingPage").then((m) => ({ default: m.PaperTradingPage })),
);
const PaperOrderPage = lazy(() =>
  import("./pages/PaperOrderPage").then((m) => ({ default: m.PaperOrderPage })),
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
const PerformancePage = lazy(() =>
  import("./pages/PerformancePage").then((m) => ({ default: m.PerformancePage })),
);
const RecommendationLabPage = lazy(() => import("./pages/RecommendationLabPage"));
const DiagnosticsPage = lazy(() =>
  import("./pages/Diagnostics").then((m) => ({ default: m.DiagnosticsPage })),
);
const AdminPanelPage = lazy(() =>
  import("./components/admin/AdminPanelPage").then((m) => ({ default: m.AdminPanelPage })),
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

  const [progressData, setProgressData] = useState({
    stage: "Initializing...",
    progress: 0,
    current_symbol: "",
    worker_id: undefined as number | undefined,
    done: 0,
    remaining: 0,
    eta_sec: 0,
  });
  const [scanStartTime, setScanStartTime] = useState<number | null>(null);
  const [lastScanDuration, setLastScanDuration] = useState<number | null>(null);

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
      import("./utils/researchPrefetcher").then(({ markPrefetched }) => markPrefetched(symbol));
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
    function loadAndApply(force = true) {
      // Always force-fetch the newest completed scan on mount/refresh so
      // sessionStorage SWR cannot restore an older historical scan.
      void loadLatestScan({ force }).then((saved) => {
        if (!saved) return;
        applyScanResult(saved, "restored");
      });
    }

    loadAndApply(true);

    const intervalId = setInterval(() => {
      console.info("[scanner] 30-min auto-polling new cached scan...");
      loadAndApply(true);
    }, 30 * 60 * 1000);

    return () => clearInterval(intervalId);
  }, []);

  useEffect(() => {
    void fetchUniverses().then(setUniverses).catch((err) => console.warn("Failed to load universes", err));
  }, []);

  // Deep-link: /scanner?symbol=RELIANCE opens stock detail (only on initial load)
  const initialLoad = useRef(true);
  useEffect(() => {
    if (initialLoad.current && symbolParam) {
      initialLoad.current = false;
      setSelectedSymbol(symbolParam.toUpperCase());
      setDetailViewOpen(true);
    }
  }, [symbolParam]);

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
      .filter((row) => {
        // Keep analysis-failed rows visible under REJECT; do not invent Score=100.
        if (row.score === null || row.score === undefined) {
          return filters.signal === "REJECT" || filters.signal === "ALL";
        }
        return row.score >= filters.scoreRange[0] && row.score <= filters.scoreRange[1];
      })
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
    // Keep timestamp card and table aligned even if one field is missing.
    const completedAt =
      response.last_scan_completed_at ??
      response.scanned_at ??
      response.analysis?.generated_at ??
      null;
    if (completedAt) {
      response.last_scan_completed_at = completedAt;
      response.scanned_at = response.scanned_at ?? completedAt;
    }

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
    setProgressData({
      stage: "Connecting data feed...",
      progress: 0,
      current_symbol: "",
      worker_id: undefined,
      done: 0,
      remaining: 0,
      eta_sec: 0,
    });
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
        (update) => {
          if (typeof update === "object") {
            setProgressData((prev) => ({
              ...prev,
              stage: update.stage || prev.stage,
              progress: update.progress ?? prev.progress,
              current_symbol: update.current_symbol ?? prev.current_symbol,
              worker_id: update.worker_id ?? prev.worker_id,
              done: update.done ?? prev.done,
              remaining: update.remaining ?? prev.remaining,
              eta_sec: update.eta_sec ?? prev.eta_sec,
            }));
          } else {
            setProgressData((prev) => ({ ...prev, stage: String(update), progress: 0 }));
          }
        },
      );

      if (scanStartTime) setLastScanDuration(Math.round((Date.now() - scanStartTime) / 1000));
      // Ensure "Last Scan Completed" and results stay on this run across F5.
      invalidateLatestScanCaches();
      cacheLatestScanFromScreenerResponse(response);
      applyScanResult(response, "fresh");
      toast.success("Scan complete", `${response.buy_candidate_symbols?.length ?? 0} BUY · ${response.watch_candidate_symbols?.length ?? 0} WATCH`);
    } catch (requestError: any) {
      if (requestError?.scanInProgress) {
        toast.info("Scanner is already running. Please wait for it to complete.");
        return;
      }
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

  function loadSavedScan(scan: any) {
    setSelectedUniverse(scan.universe ?? "NIFTY500");
    setTimeframe(scan.timeframe ?? "1d");
    setLookback(scan.lookback_window ?? 180);
    setTopN(scan.top_n ?? 20);
    navigate("/scanner");
  }

  const sendRowToPaperTrading = useCallback((row: CandidateRow, suggestedEntry?: number | null) => {
    const prefill = buildPaperTradingPrefill(row, "BUY");
    const updatedPrefill = {
      ...prefill,
      suggested_entry: suggestedEntry ?? prefill.suggested_entry,
    };

    // Dedicated full-page order ticket — never open a drawer on Scanner
    navigateToPaperOrder(navigate, {
      symbol: row.symbol,
      side: "BUY",
      prefill: updatedPrefill,
      currentPrice: suggestedEntry ?? updatedPrefill.suggested_entry ?? null,
      signal: String(row.signal ?? "BUY"),
      score: row.score ?? null,
      confidence: row.confidence ?? null,
      riskReward: row.riskReward ?? null,
      returnTo: `${window.location.pathname}${window.location.search || ""}`,
    });
  }, [navigate]);

  const scannerListView = useMemo(() => (
    <div className="scanner-center">
      {/* Row 1: Title (left) + CTA & status chips (right) — trading-desk header */}
      <header className="scanner-page-header" data-testid="scanner-page-header">
        <div className="scanner-page-header__left">
          <p className="ds-label">Scanner</p>
          <h1 className="ds-display">Scanner</h1>
          <p className="ds-muted">
            Favorites and scan results from the shared swing scanner.
          </p>
        </div>

        <div className="scanner-page-header__right">
          <div className="scanner-page-header__cta">
            <button
              type="button"
              className="button ghost-button scanner-page-header__run-btn"
              onClick={() => navigate("/markets")}
              data-testid="scanner-run-from-markets"
            >
              Run from Markets
            </button>
          </div>
          <StatusCards
            compact
            className="scanner-page-header__status"
            lastScanAt={
              screenerResult?.last_scan_completed_at ??
              screenerResult?.scanned_at ??
              screenerResult?.analysis?.generated_at ??
              null
            }
            isLoading={isLoading}
            scannedSymbols={screenerResult?.scanned_symbols ?? null}
            durationSec={lastScanDuration}
          />
        </div>
      </header>

      {/* Row 2: Result view tabs */}
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
          data={progressData}
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
            description="Adjust signal, score range, or search from Markets to refine results."
            primaryAction={{ label: "Open Markets", onClick: () => navigate("/markets"), variant: "secondary" }}
          />
        ) : null
      ) : null}

      {!screenerResult && !isLoading && !error ? (
        <EmptyState
          title="No scan results yet"
          description="Configure and run the swing scanner from Markets. Results will appear here automatically."
          primaryAction={{ label: "Go to Markets", onClick: () => navigate("/markets"), variant: "trade" }}
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
  ), [
    handleRunScanner, handleSelectSymbol, navigate,
    screenerResult, isLoading, error, showAllAnalyzedStocks,
    analysisItems, filteredRows, selectedRow?.symbol,
    progressData, scanStartTime, lastScanDuration,
  ]);

  const scannerView = (
    <main className="page-container" key="scanner-view">
      <div style={{ display: detailViewOpen && selectedRow ? "block" : "none" }}>
        <Suspense fallback={<ViewFallback />}>
          {selectedRow && (
            <StockDetailPanel
              row={selectedRow}
              onBack={handleDetailBack}
              onSendToPaperTrading={sendRowToPaperTrading}
            />
          )}
        </Suspense>
      </div>
      <div style={{ display: detailViewOpen && selectedRow ? "none" : "block" }}>
        {scannerListView}
      </div>
    </main>
  );

  const paperDeskView = useMemo(() => (
    <div className="page-container page-container--wide" key="paper-desk">
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
  ), [paperTradingPrefill, shortlistRows, screenerResult?.analysis?.generated_at]);

  const profileView = useMemo(() => (
    <Suspense fallback={<ViewFallback />} key="profile">
      <UserProfilePage
        retailMode
        onNavigate={(view) => {
          if (view === "scanner") navigate("/scanner");
          else if (view === "paper-trading") navigate("/paper");
          else navigate("/markets");
        }}
      />
    </Suspense>
  ), [navigate]);

  return (
    <FeaturePermissionsProvider>
      <PaperOrderProvider>
        <AppShell>
          <Suspense fallback={<ViewFallback />}>
            <Routes>
              {/* Ungated core landing (audit M-4) — avoid defaulting into a gated route */}
              <Route path="/" element={<Navigate to="/markets" replace />} />
              <Route path="/home" element={<Navigate to="/markets" replace />} />
              <Route
                path="/markets"
                element={
                  <Suspense fallback={<ViewFallback />}>
                    <MarketsPage
                      onLoadSavedScan={loadSavedScan}
                      screenerResult={screenerResult}
                      isLoading={isLoading}
                      scanError={error}
                      selectedUniverse={selectedUniverse}
                      timeframe={timeframe}
                      summaryMetrics={summaryMetrics}
                      onRunScanner={handleRunScanner}
                      search={filters.search}
                      onSearchChange={handleSearchChange}
                      topN={topN}
                      lookback={lookback}
                      universe={selectedUniverse}
                      universes={universesMapped}
                      onTopNChange={setTopN}
                      onLookbackChange={setLookback}
                      onTimeframeChange={setTimeframe}
                      onUniverseChange={setSelectedUniverse}
                      theme={theme}
                      onThemeToggle={toggleTheme}
                      progressData={progressData}
                      scanStartTime={scanStartTime}
                    />
                  </Suspense>
                }
              />
              <Route
                path="/scanner"
                element={
                  <FeatureGuard feature="advanced_scanner" fallback={<AccessDenied />}>
                    {scannerView}
                  </FeatureGuard>
                }
              />
              <Route path="/watchlist" element={<Navigate to="/paper?tab=watchlist" replace />} />
              <Route path="/paper" element={paperDeskView} />
              <Route path="/paper/:section" element={paperDeskView} />
              <Route
                path="/paper-order"
                element={
                  <Suspense fallback={<ViewFallback />}>
                    <PaperOrderPage />
                  </Suspense>
                }
              />
              <Route
                path="/performance"
                element={
                  <FeatureGuard feature="portfolio_analytics" fallback={<AccessDenied />}>
                    <Suspense fallback={<ViewFallback />}>
                      <PerformancePage />
                    </Suspense>
                  </FeatureGuard>
                }
              />
              <Route
                path="/recommendation-lab"
                element={
                  <FeatureGuard feature="recommendation_lab" fallback={<AccessDenied />}>
                    <Suspense fallback={<ViewFallback />}>
                      <RecommendationLabPage />
                    </Suspense>
                  </FeatureGuard>
                }
              />
              <Route
                path="/diagnostics"
                element={
                  <Suspense fallback={<ViewFallback />}>
                    <DiagnosticsPage />
                  </Suspense>
                }
              />
              <Route path="/profile" element={profileView} />
              <Route path="/logs" element={<Navigate to="/admin/logs" replace />} />
              <Route
                path="/admin"
                element={
                  <AdminRoute>
                    <Suspense fallback={<ViewFallback />}>
                      <AdminPanelPage />
                    </Suspense>
                  </AdminRoute>
                }
              />
              <Route
                path="/admin/logs"
                element={
                  <AdminRoute>
                    <FeatureGuard feature="system_logs" fallback={<AccessDenied />}>
                      <Suspense fallback={<ViewFallback />}>
                        <SystemLogs />
                      </Suspense>
                    </FeatureGuard>
                  </AdminRoute>
                }
              />
              <Route
                path="/admin/command"
                element={
                  <AdminRoute>
                    <FeatureGuard feature="central_command" fallback={<AccessDenied />}>
                      <Suspense fallback={<ViewFallback />}>
                        <CentralCommand />
                      </Suspense>
                    </FeatureGuard>
                  </AdminRoute>
                }
              />
              <Route path="/fyers/callback" element={<FyersCallback />} />
              <Route path="*" element={<Navigate to="/markets" replace />} />
            </Routes>
          </Suspense>
        </AppShell>
        {/* Global BUY/SELL bus → dedicated /paper-order page (no drawer) */}
        <PaperOrderRouteBridge />
      </PaperOrderProvider>
    </FeaturePermissionsProvider>
  );
}

/** Listens for paper:open-order and navigates to the full-page order ticket. */
function PaperOrderRouteBridge() {
  const navigate = useNavigate();

  useEffect(() => {
    const handler = (ev: Event) => {
      const detail = (ev as CustomEvent).detail || {};
      navigateToPaperOrder(navigate, {
        symbol: detail.symbol,
        side: detail.side ?? "BUY",
        prefill: detail.prefill ?? null,
        orderId: detail.orderId ?? null,
        returnTo: detail.returnTo,
        currentPrice: detail.currentPrice ?? null,
        signal: detail.signal ?? null,
        score: detail.score ?? null,
        confidence: detail.confidence ?? null,
        riskReward: detail.riskReward ?? null,
      });
    };
    window.addEventListener("paper:open-order", handler);
    return () => window.removeEventListener("paper:open-order", handler);
  }, [navigate]);

  return null;
}

function buildPaperTradingPrefill(row: CandidateRow, side?: "BUY" | "SELL"): RecommendationPrefillRequest {
  const plan =
    row.analysisItem?.recommendation.trade_plans.find((item) => item.mode === "swing") ??
    row.analysisItem?.recommendation.trade_plans[0];
  let suggested_stop: number | null = plan?.stop_loss ?? row.stopLoss ?? null;
  let suggested_targets: number[] = [plan?.target_1, plan?.target_2].filter(
    (value): value is number => typeof value === "number",
  );
  if (plan && side) {
    const needsSwap =
      (side === "BUY" && plan.bias === "short") || (side === "SELL" && plan.bias === "long");
    if (needsSwap && plan.target_1 != null && plan.stop_loss != null) {
      suggested_stop = plan.target_1;
      suggested_targets = [plan.stop_loss, plan.target_2].filter(
        (value): value is number => typeof value === "number",
      );
    }
  }
  return {
    symbol: row.symbol,
    suggested_entry: plan ? (plan.entry_low + plan.entry_high) / 2 : row.entryLow,
    suggested_stop,
    suggested_targets,
    recommendation_meta: {
      signal: row.signal,
      score: row.score ?? 0,
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

    const rec = analysis?.recommendation;
    const riskFactors = rec?.reasoning?.risk_factors ?? [];
    const hasPlans = Boolean(plan) || Boolean(rec?.trade_plans?.length);
    const analysisFailed =
      !analysis ||
      riskFactors.some((r) => typeof r === "string" && r.toLowerCase().includes("analysis failed")) ||
      // Backend clears score/plans on true analysis failure (never invent Score=100).
      (Boolean(rec) && rec!.score === 0 && !hasPlans);

    // NEVER fall back to screener_score as the recommendation score.
    // Screener scores can hit 100 and look like a fake "perfect" composite.
    // Only use the real composite score from the completed analysis pipeline.
    const compositeScore = analysisFailed
      ? null
      : typeof rec?.score === "number"
        ? rec.score
        : null;

    return {
      rank: ranking?.rank ?? null,
      symbol,
      signal,
      score: compositeScore,
      confidence: analysisFailed ? null : rec?.confidence ?? null,
      entryLow: plan?.entry_low ?? null,
      entryHigh: plan?.entry_high ?? null,
      stopLoss: plan?.stop_loss ?? null,
      target1: plan?.target_1 ?? null,
      target2: plan?.target_2 ?? null,
      riskReward: plan?.risk_reward_ratio ?? null,
      analysisFailed: Boolean(analysisFailed),
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
  return (right.score ?? -1) - (left.score ?? -1);
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



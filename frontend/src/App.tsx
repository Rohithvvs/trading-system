import { useEffect, useMemo, useState } from "react";

import { fetchSavedScans, fetchUniverses, loadLatestScan, runPresetScreener, saveScannerPreset } from "./api";
import { AllAnalyzedStocksTable } from "./components/AllAnalyzedStocksTable";
import { CandidateTable } from "./components/CandidateTable";
import { DashboardHeader } from "./components/DashboardHeader";
import { FilterBar } from "./components/FilterBar";
import { PaperTradingPage } from "./components/PaperTradingPage";
import { StockDetailPanel } from "./components/StockDetailPanel";
import { SummaryRow } from "./components/SummaryRow";
import { WorkstationPage } from "./components/WorkstationPage";
import type {
  CandidateRow,
  DashboardFilters,
  MainAppView,
  RankingItem,
  RecommendationPrefillRequest,
  ScanHistoryItem,
  ScreenerConditionResult,
  ScreenerResponse,
  SortKey,
  StockAnalysisResult,
  ThemeMode,
} from "./types";

const DEFAULT_FILTERS: DashboardFilters = {
  signal: "ALL",
  search: "",
  scoreRange: [0, 100],
  sortBy: "rank",
  onlyHighConfidence: false,
};

export default function App() {
  const [mainView, setMainView] = useState<MainAppView>("home");
  const [theme, setTheme] = useState<ThemeMode>("dark");
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
  const [lastScanLabel, setLastScanLabel] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    void loadLatestScan().then((saved) => {
      if (!saved) {
        return;
      }
      applyScanResult(saved, "restored");
    });
  }, []);

  useEffect(() => {
    void fetchUniverses().then(setUniverses).catch((err) => console.warn("Failed to load universes", err));
  }, []);

  const marketStatus = useMemo(() => getMarketStatus(), []);
  const analysisItems = screenerResult?.analysis?.items ?? [];
  const shortlistRows = useMemo(
    () => buildCandidateRows(screenerResult),
    [screenerResult],
  );

  const filteredRows = useMemo(() => {
    const searchTerm = filters.search.trim().toUpperCase();
    return shortlistRows
      .filter((row) => {
        if (filters.signal === 'ALL') return true;
        const sig = (row.signal || '').toLowerCase().trim();
        if (filters.signal === 'BUY')    return sig === 'buy'    || sig === 'bullish';
        if (filters.signal === 'WATCH')  return sig === 'watch'  || sig === 'neutral' || sig === 'sideways';
        if (filters.signal === 'REJECT') return sig === 'reject' || sig === 'bearish' || sig === 'sell';
        return true;
      })
      .filter((row) => row.score >= filters.scoreRange[0] && row.score <= filters.scoreRange[1])
      .filter((row) => (filters.onlyHighConfidence ? (row.confidence ?? 0) >= 0.7 : true))
      .filter((row) => (searchTerm ? row.symbol.includes(searchTerm) : true))
      .sort((left, right) => compareRows(left, right, filters.sortBy));
  }, [filters, shortlistRows]);

  const selectedRow = useMemo(() => {
    if (!filteredRows.length) {
      return null;
    }
    return filteredRows.find((row) => row.symbol === selectedSymbol) ?? filteredRows[0];
  }, [filteredRows, selectedSymbol]);

  const summaryMetrics = useMemo(() => {
    const shortlistedCount = screenerResult?.shortlisted_symbols.length ?? 0;
    const buyCount = screenerResult?.buy_candidate_symbols.length ?? 0;
    const watchCount = screenerResult?.watch_candidate_symbols.length ?? 0;
    const rejectedCount = Math.max(shortlistedCount - buyCount - watchCount, 0);

    return [
      { label: "Total scanned", value: screenerResult?.scanned_symbols ?? "--", helper: "Stocks checked in the Nifty 500 universe." },
      { label: "Data valid", value: screenerResult?.data_valid_symbols.length ?? "--", helper: "Names with enough clean OHLCV history for scoring." },
      { label: "Broad trend matched", value: screenerResult?.eligible_symbols.length ?? "--", helper: "Names passing the broad trend gate.", tone: "positive" as const },
      { label: "Shortlisted", value: shortlistedCount || "--", helper: "Top set moved into deeper analysis." },
      { label: "BUY candidates", value: buyCount || "--", helper: "Actionable swing ideas right now.", tone: "positive" as const },
      { label: "WATCH candidates", value: watchCount || "--", helper: "Promising names needing cleaner confirmation.", tone: "warning" as const },
      { label: "Rejected", value: rejectedCount || "--", helper: "Shortlisted names that failed final recommendation.", tone: "negative" as const },
    ];
  }, [screenerResult]);

  async function handleRunScanner() {
    setIsLoading(true);
    setError(null);

    try {
      console.info("[scanner] handleRunScanner triggered", {
        timeframe,
        lookback,
        topN,
      });
      const response = await runPresetScreener(
        "swing",
        {
          intraday: "5m",
          swing: timeframe,
          lookback_window: lookback,
        },
        selectedUniverse === "NIFTY500" ? [] : universes.find((item) => item.name === selectedUniverse)?.symbols ?? [],
        topN,
      );

      console.info("[scanner] storing scanner result", {
        scanned: response.scanned_symbols,
        shortlisted: response.shortlisted_symbols.length,
        buy: response.buy_candidate_symbols.length,
        watch: response.watch_candidate_symbols.length,
        visibleAnalysisItems: response.analysis?.items.length ?? 0,
      });

      applyScanResult(response, "fresh");
    } catch (requestError: any) {
      console.error("[scanner] scanner request failed", requestError);
      const detail = requestError?.response?.data?.detail || requestError?.detail || null;

      let errorMessage = "Scanner failed. Please try again.";

      if (detail?.error_type === "FYERS_TOKEN_EXPIRED") {
        errorMessage = "🔴 Fyers Access Token Expired — Please re-authenticate with Fyers and restart the backend.";
      } else if (detail?.error_type === "FYERS_TOKEN_INVALID") {
        errorMessage = "🔴 Fyers Token Invalid — Your Fyers API credentials are wrong. Check your config file.";
      } else if (detail?.error_type === "FYERS_RATE_LIMIT") {
        errorMessage = "⚠️ Fyers Rate Limit Hit — Please wait 60 seconds and try again.";
      } else if (detail?.error_type === "FYERS_API_ERROR") {
        errorMessage = `🔴 Fyers API Error — ${detail.message}`;
      } else if (detail?.message) {
        errorMessage = `❌ Error: ${detail.message}`;
      } else if (typeof requestError?.message === "string") {
        errorMessage = `❌ ${requestError.message}`;
      }

      setError(errorMessage);
    } finally {
      console.info("[scanner] handleRunScanner completed");
      setIsLoading(false);
    }
  }

  async function handleSaveCurrentScan() {
    const name = savedScanName.trim() || `${selectedUniverse} ${timeframe} scan`;
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
  }

  function handleExportCsv() {
    const rows = screenerResult?.all_analyzed_stocks?.length ? screenerResult.all_analyzed_stocks : screenerResult?.matches ?? [];
    if (!rows.length) return;
    const headers = ["symbol", "close", "screener_score", "technical_signal", "matched", "volume"];
    const csv = [headers.join(","), ...rows.map((row: any) => headers.map((key) => JSON.stringify(row[key] ?? "")).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `scan-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function loadSavedScan(scan: any) {
    setSelectedUniverse(scan.universe ?? "NIFTY500");
    setTimeframe(scan.timeframe ?? "1d");
    setLookback(scan.lookback_window ?? 180);
    setTopN(scan.top_n ?? 20);
    setMainView("scanner");
  }

  function applyScanResult(response: ScreenerResponse, source: "fresh" | "restored") {
    setScreenerResult(response);
    setScanHistory((current) => saveScanHistory(response, current));
    setSelectedSymbol(response.shortlisted_symbols[0] ?? response.buy_candidate_symbols[0] ?? response.watch_candidate_symbols[0] ?? null);
    setDetailViewOpen(false);
    setLastScanLabel(source === "restored" ? "Restored from saved" : null);
  }

  return (
    <div className="app-shell">
      <div className="main-nav-bar">
        <div className="main-nav-inner">
          <button data-testid="nav-scanner" type="button" className={`main-nav-tab ${mainView === "scanner" ? "is-active" : ""}`} onClick={() => setMainView("scanner")}>
            Scanner
          </button>
          <button data-testid="nav-home" type="button" className={`main-nav-tab ${mainView === "home" ? "is-active" : ""}`} onClick={() => setMainView("home")}>
            Home
          </button>
          <button data-testid="nav-paper-trading" type="button" className={`main-nav-tab ${mainView === "paper-trading" ? "is-active" : ""}`} onClick={() => setMainView("paper-trading")}>
            Paper Trading
          </button>
        </div>
      </div>

      {mainView === "scanner" ? (
        <DashboardHeader
          isLoading={isLoading}
          lastScanAt={screenerResult?.analysis?.generated_at ?? null}
          lastScanLabel={lastScanLabel}
          marketStatus={marketStatus}
          search={filters.search}
          onSearchChange={(value) => setFilters((current) => ({ ...current, search: value }))}
          onRunScanner={handleRunScanner}
          topN={topN}
          lookback={lookback}
          timeframe={timeframe}
          universe={selectedUniverse}
          universes={universes.map(({ name, count }) => ({ name, count }))}
          onTopNChange={setTopN}
          onLookbackChange={setLookback}
          onTimeframeChange={setTimeframe}
          onUniverseChange={setSelectedUniverse}
          theme={theme}
          onThemeToggle={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
        />
      ) : null}

      <div className="app-main-scroll">
        {mainView === "home" ? (
          <WorkstationPage onLoadSavedScan={loadSavedScan} />
        ) : mainView === "paper-trading" ? (
          <div className="dashboard-grid">
            <PaperTradingPage
              recommendationPrefill={paperTradingPrefill}
              onPrefillConsumed={() => setPaperTradingPrefill(null)}
              scannerCandidates={shortlistRows}
              lastScanAt={screenerResult?.analysis?.generated_at ?? null}
            />
          </div>
        ) : detailViewOpen && selectedRow ? (
          <main className="detail-screen-layout">
            <StockDetailPanel
              row={selectedRow}
              onBack={() => setDetailViewOpen(false)}
              onSendToPaperTrading={(row, suggestedEntry) => {
                const plan = row.analysisItem?.recommendation.trade_plans.find((item) => item.mode === "swing") ?? row.analysisItem?.recommendation.trade_plans[0];
                setPaperTradingPrefill({
                  symbol: row.symbol,
                  suggested_entry: suggestedEntry ?? (plan ? (plan.entry_low + plan.entry_high) / 2 : row.entryLow),
                  suggested_stop: plan?.stop_loss ?? row.stopLoss ?? null,
                  suggested_targets: [plan?.target_1, plan?.target_2].filter((value): value is number => typeof value === "number"),
                  recommendation_meta: {
                    signal: row.signal,
                    score: row.score,
                    confidence: Math.round((row.confidence ?? 0) * 100) / 100,
                  },
                });
                setMainView("paper-trading");
              }}
            />
          </main>
        ) : (
          <main className="dashboard-grid">
            <SummaryRow metrics={summaryMetrics} />

            {screenerResult?.data_warning ? (
              <section className="panel warning-box">
                <strong>Data source warning</strong>
                <p>{screenerResult.data_warning}</p>
              </section>
            ) : null}

            {!showAllAnalyzedStocks ? <FilterBar filters={filters} onChange={setFilters} /> : null}

            <section className="panel scanner-actions">
              <label className="inline-field">
                <span>Save scan name</span>
                <input placeholder="Momentum pullback scan" value={savedScanName} onChange={(event) => setSavedScanName(event.target.value)} />
              </label>
              <button type="button" className="button ghost-button" onClick={() => void handleSaveCurrentScan()}>Save Scan</button>
              <button type="button" className="button ghost-button" onClick={handleExportCsv} disabled={!screenerResult}>Export CSV</button>
            </section>

            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
              <button
                type="button"
                className={`button ${!showAllAnalyzedStocks ? "primary-button" : ""}`}
                onClick={() => setShowAllAnalyzedStocks(false)}
              >
                Shortlisted ({screenerResult?.shortlisted_symbols.length ?? 0})
              </button>
              <button
                type="button"
                className={`button ${showAllAnalyzedStocks ? "primary-button" : ""}`}
                onClick={() => setShowAllAnalyzedStocks(true)}
              >
                All Analyzed ({screenerResult?.all_analyzed_stocks?.length ?? 0})
              </button>
            </div>

            {isLoading ? (
              <section className="panel loading-state">
                <h2>Running scanner</h2>
                <ol>
                  <li>Fetching OHLCV for the configured Nifty 500 universe.</li>
                  <li>Validating data quality and broad trend eligibility.</li>
                  <li>Scoring the shortlist and running full analysis on the top set.</li>
                </ol>
              </section>
            ) : null}

            {error ? (
              <div style={{
                background: "#fee2e2",
                border: "1px solid #f87171",
                borderRadius: "8px",
                padding: "12px 16px",
                color: "#991b1b",
                fontWeight: 600,
                fontSize: "14px",
                margin: "12px 0"
              }}>
                <div>{error}</div>
                <div style={{ marginTop: 8 }}>
                  <button type="button" className="button primary-button" onClick={handleRunScanner}>
                    Retry scan
                  </button>
                </div>
              </div>
            ) : null}

            {!isLoading && !error ? (
              showAllAnalyzedStocks ? (
                <AllAnalyzedStocksTable stocks={screenerResult?.all_analyzed_stocks ?? []} />
              ) : (
                <CandidateTable
                  rows={filteredRows}
                  selectedSymbol={selectedRow?.symbol ?? null}
                  onSelect={(symbol) => {
                    setSelectedSymbol(symbol);
                    setDetailViewOpen(true);
                  }}
                />
              )
            ) : null}

            {!screenerResult && !isLoading && !error ? (
              <section className="panel empty-state intro-state">
                <h2>Ready for the next scan</h2>
                <p>This dashboard is built for one workflow: scan the Nifty 500, shortlist the best swing candidates, and inspect one stock in execution-ready detail.</p>
                <div className="intro-grid">
                  <article>
                    <strong>1. Run scanner</strong>
                    <p>Pull fresh data, validate it, and score the universe.</p>
                  </article>
                  <article>
                    <strong>2. Review shortlist</strong>
                    <p>Filter BUY, WATCH, and REJECT outcomes in one table.</p>
                  </article>
                  <article>
                    <strong>3. Open a stock</strong>
                    <p>Click the stock row to open a dedicated full-detail review screen.</p>
                  </article>
                </div>
              </section>
            ) : null}

            {screenerResult ? (
              <section className="panel footer-note">
                <p>
                  <strong>{screenerResult.screener_name}</strong> is advisory only. The dashboard prioritizes usability and explainability, but you still make the final manual trading decision.
                </p>
                <p>
                  Sample rows: {analysisItems.length} analyzed | {filteredRows.length} visible after filters.
                </p>
              </section>
            ) : null}

            <ScanHistoryPanel
              history={scanHistory}
            />
          </main>
        )}
      </div>
    </div>
  );
}

function buildCandidateRows(screenerResult: ScreenerResponse | null): CandidateRow[] {
  if (!screenerResult) {
    return [];
  }

  const analysisBySymbol = new Map<string, StockAnalysisResult>();
  const matchBySymbol = new Map<string, ScreenerConditionResult>();
  const rankingBySymbol = new Map<string, RankingItem>();

  screenerResult.analysis?.items.forEach((item) => {
    analysisBySymbol.set(item.symbol, item);
  });
  screenerResult.matches.forEach((match) => {
    matchBySymbol.set(match.symbol, match);
  });
  screenerResult.analysis?.rankings.rankings.forEach((ranking) => {
    rankingBySymbol.set(ranking.symbol, ranking);
  });

  return screenerResult.shortlisted_symbols.map((symbol) => {
    const analysis = analysisBySymbol.get(symbol);
    const match = matchBySymbol.get(symbol);
    const ranking = rankingBySymbol.get(symbol);
    const plan = analysis?.recommendation.trade_plans.find((item) => item.mode === "swing") ?? analysis?.recommendation.trade_plans[0];
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
  const item: ScanHistoryItem = {
    id: `${response.analysis?.generated_at ?? new Date().toISOString()}-${response.shortlisted_symbols.join("-")}`,
    generated_at: response.analysis?.generated_at ?? new Date().toISOString(),
    screener_name: response.screener_name,
    scanned_symbols: response.scanned_symbols,
    shortlisted_count: response.shortlisted_symbols.length,
    buy_symbols: response.buy_candidate_symbols,
    watch_symbols: response.watch_candidate_symbols,
    data_source: response.data_source,
    data_warning: response.data_warning,
  };
  const next = [item, ...current.filter((entry) => entry.id !== item.id)].slice(0, 20);
  window.localStorage.setItem("scanHistory", JSON.stringify(next));
  return next;
}

function ScanHistoryPanel({
  history,
}: {
  history: ScanHistoryItem[];
}) {
  if (!history.length) {
    return null;
  }
  return (
    <section className="panel scan-history-panel">
      <div className="panel-header">
        <div>
          <p className="section-label">Scan history</p>
          <h2>Recent scanner snapshots</h2>
        </div>
      </div>
      <div className="scan-history-list">
        {history.slice(0, 5).map((item) => (
          <article key={item.id} className="scan-history-item">
            <div>
              <strong>{new Date(item.generated_at).toLocaleString()}</strong>
              <p>{item.shortlisted_count} shortlisted from {item.scanned_symbols} scanned | source {item.data_source ?? "unknown"}</p>
            </div>
            <div className="scan-history-symbols">
              {[...item.buy_symbols, ...item.watch_symbols].slice(0, 6).map((symbol) => (
                <span key={`${item.id}-${symbol}`} className="helper-chip">
                  {symbol}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function compareRows(left: CandidateRow, right: CandidateRow, sortBy: SortKey) {
  if (sortBy === "rank") {
    return (left.rank ?? 999) - (right.rank ?? 999);
  }
  if (sortBy === "confidence") {
    return (right.confidence ?? -1) - (left.confidence ?? -1);
  }
  if (sortBy === "riskReward") {
    return (right.riskReward ?? -1) - (left.riskReward ?? -1);
  }
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
  if (!technical && !match) {
    return "n/a";
  }
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
  if (!match) {
    return "n/a";
  }
  return match.conditions.volume_above_previous_day ? "expanding" : "adequate";
}

function getMarketStatus() {
  const now = new Date();
  const day = now.getDay();
  const minutes = now.getHours() * 60 + now.getMinutes();
  const open = 9 * 60 + 15;
  const close = 15 * 60 + 30;

  if (day === 0 || day === 6) {
    return "Closed";
  }
  if (minutes >= open && minutes <= close) {
    return "Open";
  }
  return "Closed";
}

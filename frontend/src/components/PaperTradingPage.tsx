import { lazy, Suspense, useEffect, useMemo, useState, useRef, memo } from "react";
import { useNavigate } from "react-router-dom";
import { InfoTooltip } from './InfoTooltip';
import { TOOLTIPS } from '../constants/tooltips';
import { apiUrl } from '../config';
import { navigateToPaperOrder } from "../utils/paperOrderNavigation";
import { WatchlistTab } from './WatchlistTab';

const DailyAnalyticsPanel = lazy(() =>
  import("./DailyAnalyticsPanel").then((m) => ({ default: m.DailyAnalyticsPanel })),
);
const AnalyticsPanel = lazy(() =>
  import("./AnalyticsPanel").then((m) => ({ default: m.AnalyticsPanel })),
);

import {
  cancelPaperOrder,
  closePaperPosition,
  fetchPaperTradingDashboard,
  fetchPaperAccountSummary,
  updatePaperAccountCapital,
  fetchPaperAccountTransactions,
  fetchPaperQuote,
  placePaperOrder,
  updatePaperOrder,
  deletePaperOrder,
  prefillPaperTrade,
  resetPaperTradingAccount,
  updatePaperPosition,
  fetchPositions,
  fetchPendingPaperOrders,
  fetchPaperTrades,
  squareOffAllPositions,
  fetchUnreadNotifications,
  markNotificationsRead,
  fetchAlerts,
  createAlert,
  deleteAlert,
  getTokenStatus,
  fetchMarketEngineStatus,
  startMarketEngine,
  stopMarketEngine,
  invalidatePaperCaches,
} from "../api";
import { checkCanPlaceBuyOrder, showMarketClosedAlert } from "../utils/tradingHours";
import TokenStatus from "./TokenStatus";
import { MetricCardSkeleton, TableSkeleton, ChartSkeleton } from "./Skeleton";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import type {
  CandidateRow,
  PaperOrder,
  PaperOrderTicketState,
  PaperPosition,
  PaperTradeHistoryItem,
  PaperTradingDashboardResponse,
  RecommendationPrefillRequest,
  MarketEngineStatus,
  MarketEngineHealth,
} from "../types";
import { fetchPaperTradingEngineStatus } from "../api";

function TradeDetailsModal({ trade, onClose }: { trade: PaperTradeHistoryItem | null; onClose: () => void }) {
  if (!trade) return null;
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" onClick={onClose} onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }} tabIndex={-1} style={{ zIndex: 9999 }}>
      <div className="confirm-modal" onClick={e => e.stopPropagation()} style={{ minWidth: 400, maxWidth: 500 }}>
        <h2>Trade Exit Details</h2>
        <div style={{ marginTop: 16, marginBottom: 24, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <div className="muted-copy">Reason:</div>
            <div style={{ fontWeight: 600 }}>{trade.exit_reason ?? "MANUAL_EXIT"}</div>
          </div>
          <div>
            <div className="muted-copy">Source:</div>
            <div style={{ fontWeight: 600 }}>{trade.exit_source ?? "MANUAL"}</div>
          </div>
          <div>
            <div className="muted-copy">Exit Price:</div>
            <div style={{ fontWeight: 600 }}>₹{trade.exit_price.toFixed(2)}</div>
          </div>
          <div>
            <div className="muted-copy">Exit Time:</div>
            <div style={{ fontWeight: 600 }}>{new Date(trade.closed_at).toLocaleTimeString()}</div>
          </div>
        </div>
        
        {trade.exit_source === "RECONCILIATION" && (
          <div style={{ background: '#083544', padding: 12, borderRadius: 6, marginBottom: 24, fontSize: '0.9rem' }}>
            <strong>Recovered During Historical Reconciliation</strong>
          </div>
        )}

        <div className="modal-actions" style={{ marginTop: 0 }}>
          <button type="button" className="button ghost-button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export function MarketEngineHealthWidget({ health, lastSuccessfulPoll, errorCount }: { health: MarketEngineHealth | null; lastSuccessfulPoll: number | null; errorCount: number }) {
  if (!health && errorCount === 0) return null;

  const isStale = errorCount * 10000 > 30000;
  const displayStatus = errorCount > 0 ? 'DEGRADED' : health?.status ?? 'UNKNOWN';
  const statusColor = displayStatus === 'RUNNING' ? '🟢' : displayStatus === 'DEGRADED' ? '🟡' : '🔴';
  
  return (
    <section className="panel" style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <p className="section-label" style={{ marginBottom: 0 }}>Market Engine Status</p>
          {isStale && <span style={{ color: '#ffcc00', fontSize: '0.8rem', fontWeight: 600 }}>⚠ Data may be stale</span>}
        </div>
        <h2 style={{ fontSize: '1.2rem', marginTop: 4 }}>
          {statusColor} {displayStatus}
        </h2>
        {lastSuccessfulPoll && (
          <div style={{ fontSize: '0.8rem', color: '#8b949e', marginTop: 4 }}>
            Last Updated: {new Date(lastSuccessfulPoll).toLocaleTimeString()}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 24, textAlign: 'right' }}>
        <div>
          <div className="muted-copy">Last Tick</div>
          <div style={{ fontWeight: 600 }}>{health?.last_tick_at ? new Date(health.last_tick_at).toLocaleTimeString() : '--'}</div>
        </div>
        <div>
          <div className="muted-copy">Last Reconciliation</div>
          <div style={{ fontWeight: 600 }}>{health?.last_reconciliation_at ? new Date(health.last_reconciliation_at).toLocaleTimeString() : '--'}</div>
        </div>
        <div>
          <div className="muted-copy">Open Positions</div>
          <div style={{ fontWeight: 600 }}>{health?.open_positions ?? '--'}</div>
        </div>
        <div>
          <div className="muted-copy">Tracked Symbols</div>
          <div style={{ fontWeight: 600 }}>{health?.tracked_symbols ?? '--'}</div>
        </div>
      </div>
    </section>
  );
}

type PaperTradingPageProps = {
  recommendationPrefill?: RecommendationPrefillRequest | null;
  onPrefillConsumed?: () => void;
  scannerCandidates?: CandidateRow[];
  lastScanAt?: string | null;
  /** Hide engine/token/ops controls for retail users */
  retailMode?: boolean;
};

export type PaperPanelTab = "positions" | "orders" | "history" | "analytics" | "daily-analytics" | "alerts" | "account" | "watchlist";

const VALID_PAPER_TABS: PaperPanelTab[] = [
  "positions",
  "orders",
  "history",
  "analytics",
  "daily-analytics",
  "alerts",
  "account",
  "watchlist",
];

// Chart.js global loaded from CDN
declare const Chart: any;

const DEFAULT_TICKET: PaperOrderTicketState = {
  // Canonical cash symbol (no -EQ). Universe + quote validation use canonical form.
  symbol: "INFY",
  side: "BUY",
  type: "LIMIT",
  qty: 1,
  limitPrice: null,
  stopPrice: null,
  stopLoss: null,
  target: null,
  notes: "",
  sourceSignal: null,
  sourceScore: null,
  sourceConfidence: null,
};

function readPaperTabFromUrl(): PaperPanelTab {
  try {
    const path = window.location.pathname;
    const section = path.match(/\/paper\/([^/]+)/)?.[1];
    if (section && VALID_PAPER_TABS.includes(section as PaperPanelTab)) {
      return section as PaperPanelTab;
    }
    const q = new URLSearchParams(window.location.search).get("tab");
    if (q && VALID_PAPER_TABS.includes(q as PaperPanelTab)) return q as PaperPanelTab;
  } catch {
    /* ignore */
  }
  return "positions";
}

export function PaperTradingPage({
  recommendationPrefill,
  onPrefillConsumed,
  scannerCandidates = [],
  lastScanAt = null,
  retailMode = false,
}: PaperTradingPageProps) {
  const navigate = useNavigate();
  // Insert TokenStatus panel in account tab when active
  const urlParams = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const urlSymbol = urlParams?.get("symbol");
  const urlSide = urlParams?.get("side");
  const initialSymbol =
    recommendationPrefill?.symbol ?? urlSymbol ?? scannerCandidates[0]?.symbol ?? DEFAULT_TICKET.symbol;
  // Instant shell: seed from cache so header/tabs/metrics paint immediately
  const [dashboard, setDashboard] = useState<PaperTradingDashboardResponse | null>(
    () => getCached<PaperTradingDashboardResponse>(CACHE_KEYS.paperDashboard) ?? getCached(CACHE_KEYS.paperDashboardSymbol(initialSymbol)),
  );
  const [selectedSymbol, setSelectedSymbol] = useState<string>(initialSymbol);
  const [ticket, setTicket] = useState<PaperOrderTicketState>({
    ...DEFAULT_TICKET,
    symbol: initialSymbol,
    side: urlSide === "SELL" ? "SELL" : "BUY",
  });
  const [listTab, setListTab] = useState<PaperPanelTab>(() => readPaperTabFromUrl());
  const [resetBalance, setResetBalance] = useState(1000000);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  /** User toggle — live pricing stays enabled across transient failures. */
  const [isLivePricing, setIsLivePricing] = useState(true);
  /** Connection lifecycle for quote stream (never permanently killed on one failure). */
  const [quoteFeedStatus, setQuoteFeedStatus] = useState<
    "connecting" | "live" | "reconnecting" | "degraded" | "paused"
  >("connecting");
  const [quoteStatusDetail, setQuoteStatusDetail] = useState<string | null>(null);
  const [lastQuoteAt, setLastQuoteAt] = useState<number | null>(null);
  const [lastSuccessfulPrice, setLastSuccessfulPrice] = useState<number | null>(null);
  const quoteRetryCountRef = useRef(0);
  const quoteInFlightRef = useRef(false);
  const quoteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevQuoteSymbolRef = useRef<string | null>(null);
  const [accountSummary, setAccountSummary] = useState<any | null>(
    () => getCached(CACHE_KEYS.paperAccount),
  );
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => crypto.randomUUID());
  const [engineStatus, setEngineStatus] = useState<MarketEngineStatus | null>(
    () => getCached(CACHE_KEYS.marketEngineStatus),
  );
  const [engineHealth, setEngineHealth] = useState<MarketEngineHealth | null>(
    () => getCached(CACHE_KEYS.marketEngineHealth),
  );
  const [lastSuccessfulHealthPoll, setLastSuccessfulHealthPoll] = useState<number | null>(null);
  const [healthPollErrorCount, setHealthPollErrorCount] = useState<number>(0);
  const [selectedTrade, setSelectedTrade] = useState<PaperTradeHistoryItem | null>(null);
  const [confirmAction, setConfirmAction] = useState<null | "reset" | "square-off">(null);
  const seenNotifications = useRef<Set<number>>(new Set());

  // Keep tab in URL for deep links / refresh
  useEffect(() => {
    if (!window.location.pathname.startsWith("/paper")) return;
    const desired = listTab === "positions" ? "/paper" : `/paper/${listTab}`;
    const full = `${desired}${window.location.search || ""}`;
    if (window.location.pathname + window.location.search !== full) {
      window.history.replaceState(null, "", full);
    }
  }, [listTab]);

  // Deep link: /paper?symbol=X&side=BUY|SELL → dedicated full-page order ticket
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const side = params.get("side");
      const symbol = params.get("symbol") ?? selectedSymbol;
      if (side === "BUY" || side === "SELL") {
        navigateToPaperOrder(navigate, {
          symbol: symbol || undefined,
          side,
          returnTo: "/paper",
        });
      }
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // After successful order from Paper Order page — Positions tab + full refresh (no browser reload)
  useEffect(() => {
    const handler = (ev: Event) => {
      const detail = (ev as CustomEvent).detail || {};
      const sym = detail.symbol || selectedSymbol;
      setListTab("positions");
      setStatusMessage("✓ Paper Order Placed Successfully");
      if (sym) setSelectedSymbol(sym);
      invalidatePaperCaches();
      void (async () => {
        try {
          const [dash, summary, positions, pending, trades] = await Promise.all([
            fetchPaperTradingDashboard(sym, { force: true }).catch(() => null),
            fetchPaperAccountSummary({ force: true }).catch(() => null),
            fetchPositions().catch(() => null),
            fetchPendingPaperOrders().catch(() => null),
            fetchPaperTrades().catch(() => null),
          ]);
          if (dash) {
            setDashboard({
              ...dash,
              positions: positions ?? dash.positions,
              open_orders: pending ?? dash.open_orders,
              trades: trades ?? dash.trades,
            });
          } else if (positions || pending || trades) {
            setDashboard((current) =>
              current
                ? {
                    ...current,
                    positions: positions ?? current.positions,
                    open_orders: pending ?? current.open_orders,
                    trades: trades ?? current.trades,
                  }
                : current,
            );
          }
          if (summary) setAccountSummary(summary);
        } catch {
          /* ignore */
        }
      })();
    };
    window.addEventListener("paper:order-success", handler);
    return () => window.removeEventListener("paper:order-success", handler);
  }, [selectedSymbol]);

  // Check for offline gap replay after initial dashboard load.
  async function checkGapReplay() {
    try {
      const resp = await fetch(apiUrl("/paper-trading/gap-replay-summary"), { credentials: "include" });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.orders_filled?.length > 0 || data.positions_exited?.length > 0) {
        const msg = [
          data.orders_filled?.length > 0
            ? `${data.orders_filled.length} order(s) filled while offline`
            : null,
          data.positions_exited?.length > 0
            ? `${data.positions_exited.length} position(s) exited while offline`
            : null,
          data.warnings?.length > 0
            ? `${data.warnings.length} warning(s) — check manually`
            : null,
        ]
          .filter(Boolean)
          .join(" | ");
        setStatusMessage(`⚡ Offline Gap Replay: ${msg}`);
      }
      if (data.warnings?.length > 0) {
        console.warn("[GAP_REPLAY] Warnings:", data.warnings);
      }
    } catch {
      /* ignore network errors — backend may not be ready yet */
    }
  }

  // Parallel initial load + periodic refresh (single effect, no sequential waterfalls)
  useEffect(() => {
    let mounted = true;
    let retryTimeout: ReturnType<typeof setTimeout> | null = null;

    async function loadAll(retryCount = 0, force = false) {
      try {
        setError(null);
        const [dash, summary, engStatus, engHealth] = await Promise.all([
          fetchPaperTradingDashboard(selectedSymbol, { force }).catch((e) => {
            throw e;
          }),
          fetchPaperAccountSummary({ force }).catch(() => null),
          fetchMarketEngineStatus().catch(() => null),
          fetchPaperTradingEngineStatus().catch(() => null),
        ]);
        // Token warm in background (cached) — never blocks UI
        void getTokenStatus().catch(() => null);

        if (!mounted) return;
        if (dash) {
          setDashboard(dash);
          const wp = dash.selected_workspace?.current_price;
          if (wp != null && Number(wp) > 0) {
            setLastSuccessfulPrice(Number(wp));
            if (dash.selected_workspace?.price_fetched_at) {
              const ts = Date.parse(dash.selected_workspace.price_fetched_at);
              if (!Number.isNaN(ts)) setLastQuoteAt(ts);
            } else {
              setLastQuoteAt(Date.now());
            }
          }
        }
        if (summary) setAccountSummary(summary);
        if (engStatus) setEngineStatus(engStatus);
        if (engHealth) {
          setEngineHealth(engHealth);
          setLastSuccessfulHealthPoll(Date.now());
          setHealthPollErrorCount(0);
        }
        if (retryCount === 0) void checkGapReplay();
      } catch (err) {
        console.error("[PaperTrading] Load failed (attempt", retryCount + 1, "):", err);
        if (mounted && retryCount < 3 && !dashboard) {
          retryTimeout = setTimeout(() => void loadAll(retryCount + 1, true), 2000);
        } else if (mounted && !dashboard) {
          setError("Could not connect to server. Please refresh.");
        }
      }
    }

    void loadAll(0, false);

    const id = window.setInterval(() => {
      void (async () => {
        try {
          const [dash, summary, engStatus, engHealth] = await Promise.all([
            fetchPaperTradingDashboard(selectedSymbol, { force: true }).catch(() => null),
            fetchPaperAccountSummary({ force: true }).catch(() => null),
            fetchMarketEngineStatus().catch(() => null),
            fetchPaperTradingEngineStatus().catch(() => null),
          ]);
          if (!mounted) return;
          if (dash) setDashboard(dash);
          if (summary) setAccountSummary(summary);
          if (engStatus) setEngineStatus(engStatus);
          if (engHealth) {
            setEngineHealth(engHealth);
            setLastSuccessfulHealthPoll(Date.now());
            setHealthPollErrorCount((c) => {
              if (c > 0) console.info("ENGINE_STATUS_RECOVERED");
              return 0;
            });
          }
        } catch (err) {
          if (!mounted) return;
          console.warn("ENGINE_STATUS_POLL_FAILED", err);
          setHealthPollErrorCount((c) => {
            const next = c + 1;
            if (next * 10000 > 30000 && c * 10000 <= 30000) {
              console.warn("ENGINE_STATUS_STALE");
            }
            return next;
          });
        }
      })();
    }, 10000);

    return () => {
      mounted = false;
      if (retryTimeout) clearTimeout(retryTimeout);
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial mount + selectedSymbol handled by poll
  }, [selectedSymbol]);

  // Live quote poller with exponential backoff and automatic resume.
  // Never permanently disables pricing after a single failure.
  useEffect(() => {
    if (!isLivePricing) {
      setQuoteFeedStatus("paused");
      setQuoteStatusDetail(null);
      if (quoteTimerRef.current) {
        window.clearTimeout(quoteTimerRef.current);
        quoteTimerRef.current = null;
      }
      return undefined;
    }

    let cancelled = false;
    quoteRetryCountRef.current = 0;
    if (prevQuoteSymbolRef.current !== selectedSymbol) {
      // Symbol switch: drop prior LTP so we never show the wrong instrument's price.
      setLastSuccessfulPrice(null);
      setLastQuoteAt(null);
      prevQuoteSymbolRef.current = selectedSymbol;
    }
    setQuoteFeedStatus((prev) => (prev === "live" || prev === "degraded" ? prev : "connecting"));
    setQuoteStatusDetail((prev) => prev ?? "Connecting to Live Market...");

    const BACKOFF_MS = [1000, 2000, 5000, 10000];
    const MAX_RETRIES = BACKOFF_MS.length;
    const LIVE_INTERVAL_MS = 2000;

    const scheduleNext = (delayMs: number) => {
      if (cancelled) return;
      if (quoteTimerRef.current) {
        window.clearTimeout(quoteTimerRef.current);
      }
      quoteTimerRef.current = window.setTimeout(() => {
        void tick();
      }, delayMs);
    };

    async function tick() {
      if (cancelled || quoteInFlightRef.current) {
        scheduleNext(LIVE_INTERVAL_MS);
        return;
      }
      quoteInFlightRef.current = true;
      try {
        await loadLiveQuote(selectedSymbol);
        if (cancelled) return;
        quoteRetryCountRef.current = 0;
        scheduleNext(LIVE_INTERVAL_MS);
      } catch {
        if (cancelled) return;
        const attempt = Math.min(quoteRetryCountRef.current, MAX_RETRIES - 1);
        const delay = BACKOFF_MS[attempt] ?? BACKOFF_MS[BACKOFF_MS.length - 1];
        quoteRetryCountRef.current += 1;
        // Keep retrying indefinitely after max backoff (do not require manual refresh)
        scheduleNext(delay);
      } finally {
        quoteInFlightRef.current = false;
      }
    }

    void tick();

    return () => {
      cancelled = true;
      if (quoteTimerRef.current) {
        window.clearTimeout(quoteTimerRef.current);
        quoteTimerRef.current = null;
      }
      quoteInFlightRef.current = false;
    };
    // loadLiveQuote closes over latest dashboard via setState; symbol/toggle drive reschedule
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLivePricing, selectedSymbol]);

  useEffect(() => {
    if (!dashboard?.selected_workspace?.symbol) {
      return;
    }
    setSelectedSymbol(dashboard.selected_workspace.symbol);
    setTicket((current) => ({
      ...current,
      symbol: dashboard.selected_workspace?.symbol ?? current.symbol,
      limitPrice: current.limitPrice ?? dashboard.selected_workspace?.current_price ?? null,
    }));
  }, [dashboard?.selected_workspace?.symbol]);

  useEffect(() => {
    if (!recommendationPrefill) {
      return;
    }
    void handleExternalPrefill(recommendationPrefill);
  }, [recommendationPrefill]);

  useEffect(() => {
    const firstScannerPick = scannerCandidates[0];
    if (!firstScannerPick || selectedSymbol !== DEFAULT_TICKET.symbol) {
      return;
    }
    setSelectedSymbol(firstScannerPick.symbol);
    setTicket(buildTicketFromCandidate(firstScannerPick, ticket, workspace?.current_price ?? null, lastScanAt));
    void loadDashboard(firstScannerPick.symbol);
  }, [scannerCandidates, lastScanAt]);

  const workspace = dashboard?.selected_workspace ?? null;
  const selectedPosition = dashboard?.positions.find((item) => item.symbol === selectedSymbol) ?? null;
  const scannerCandidateMap = useMemo(
    () => new Map(scannerCandidates.map((item) => [item.symbol, item])),
    [scannerCandidates],
  );
  const scannerSymbols = useMemo(() => scannerCandidates.map((item) => item.symbol), [scannerCandidates]);
  const ticketSymbols = useMemo(
    () => uniqueSymbols([...scannerSymbols, ...(dashboard?.symbols ?? [])]),
    [dashboard?.symbols, scannerSymbols],
  );
  const selectedScannerCandidate = scannerCandidateMap.get(selectedSymbol) ?? null;
  const selectedOrders = useMemo(
    () => dashboard?.open_orders.filter((item) => item.symbol === selectedSymbol) ?? [],
    [dashboard?.open_orders, selectedSymbol],
  );

  const riskMetrics = useMemo(() => {
    const priceReference =
      ticket.type === "LIMIT"
        ? ticket.limitPrice
        : ticket.type === "STOP"
          ? ticket.stopPrice
          : workspace?.current_price ?? null;
    const estimatedCost = priceReference ? priceReference * ticket.qty : 0;
    const riskPerShare = priceReference && ticket.stopLoss ? Math.abs(priceReference - ticket.stopLoss) : 0;
    const rewardPerShare = priceReference && ticket.target ? Math.abs(ticket.target - priceReference) : 0;
    const riskAmount = riskPerShare * ticket.qty;
    const riskReward = riskPerShare > 0 ? rewardPerShare / riskPerShare : 0;
    const riskPercent =
      dashboard?.account.equity && riskAmount
        ? (riskAmount / dashboard.account.equity) * 100
        : 0;

    return {
      estimatedCost,
      riskPerShare,
      rewardPerShare,
      riskAmount,
      riskReward,
      riskPercent,
      warning:
        dashboard && riskPercent > dashboard.account.max_risk_per_trade * 100
          ? `Risk exceeds account guideline of ${(dashboard.account.max_risk_per_trade * 100).toFixed(1)}% per trade.`
          : null,
    };
  }, [dashboard, ticket, workspace?.current_price]);

  async function loadDashboard(symbol?: string, silent = false) {
    if (!silent) {
      setIsBusy(true);
    }
    setError(null);
    try {
      invalidatePaperCaches();
      const response = await fetchPaperTradingDashboard(symbol ?? selectedSymbol, { force: true });
      setDashboard(response);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load paper trading workspace.");
    } finally {
      if (!silent) {
        setIsBusy(false);
      }
    }
  }

  async function loadPositions(symbol?: string, silent = true) {
    if (!silent) {
      setIsBusy(true);
    }
    setError(null);
    try {
      if (!dashboard) {
        const response = await fetchPaperTradingDashboard(symbol ?? selectedSymbol);
        setDashboard(response);
        return;
      }
      const positions = await fetchPositions();
      setDashboard((current) => {
        if (!current) {
          return {
            account: dashboard.account,
            positions,
            open_orders: [],
            order_history: [],
            trades: [],
            symbols: dashboard.symbols,
            selected_workspace: dashboard.selected_workspace,
          } as PaperTradingDashboardResponse;
        }
        return {
          ...current,
          positions,
        } as PaperTradingDashboardResponse;
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load positions.");
    } finally {
      if (!silent) {
        setIsBusy(false);
      }
    }
  }

  async function loadPendingOrders(symbol?: string, silent = true) {
    if (!silent) {
      setIsBusy(true);
    }
    setError(null);
    try {
      if (!dashboard) {
        const response = await fetchPaperTradingDashboard(symbol ?? selectedSymbol);
        setDashboard(response);
        return;
      }
      const open_orders = await fetchPendingPaperOrders();
      setDashboard((current) => {
        if (!current) {
          return {
            account: dashboard.account,
            positions: dashboard.positions,
            open_orders,
            order_history: dashboard.order_history,
            trades: dashboard.trades,
            symbols: dashboard.symbols,
            selected_workspace: dashboard.selected_workspace,
          } as PaperTradingDashboardResponse;
        }
        return {
          ...current,
          open_orders,
        } as PaperTradingDashboardResponse;
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load open orders.");
    } finally {
      if (!silent) {
        setIsBusy(false);
      }
    }
  }

  async function loadTradeHistory(symbol?: string, silent = true) {
    if (!silent) {
      setIsBusy(true);
    }
    setError(null);
    try {
      if (!dashboard) {
        const response = await fetchPaperTradingDashboard(symbol ?? selectedSymbol);
        setDashboard(response);
        return;
      }
      const trades = await fetchPaperTrades();
      setDashboard((current) => {
        if (!current) {
          return {
            account: dashboard.account,
            positions: dashboard.positions,
            open_orders: dashboard.open_orders,
            order_history: dashboard.order_history,
            trades,
            symbols: dashboard.symbols,
            selected_workspace: dashboard.selected_workspace,
          } as PaperTradingDashboardResponse;
        }
        return {
          ...current,
          trades,
        } as PaperTradingDashboardResponse;
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to load trade history.");
    } finally {
      if (!silent) {
        setIsBusy(false);
      }
    }
  }

  async function loadLiveQuote(symbol: string) {
    // Allow quote polling even before full dashboard paint so recovery is not blocked.
    try {
      if (quoteRetryCountRef.current === 0) {
        setQuoteFeedStatus((prev) => (prev === "live" || prev === "degraded" ? prev : "connecting"));
      } else {
        setQuoteFeedStatus("reconnecting");
        setQuoteStatusDetail(
          quoteRetryCountRef.current === 1
            ? "Reconnecting..."
            : `Reconnecting... (attempt ${quoteRetryCountRef.current + 1})`,
        );
      }

      const quote = await fetchPaperQuote(symbol);
      const price = Number(quote.current_price);
      const hasPrice = Number.isFinite(price) && price > 0;
      const marketStatus = quote.market_status ?? (quote.source === "FYERS_QUOTE" ? "live" : "degraded");

      if (hasPrice) {
        setDashboard((current) => updateDashboardQuote(current, quote.symbol, price));
        setLastSuccessfulPrice(price);
        setLastQuoteAt(Date.now());
      }

      if (marketStatus === "live" && hasPrice && !quote.is_stale) {
        setQuoteFeedStatus("live");
        setQuoteStatusDetail("Live Market Connected");
      } else if (hasPrice) {
        setQuoteFeedStatus("degraded");
        setQuoteStatusDetail(quote.reason || "Waiting for Market Data...");
      } else {
        setQuoteFeedStatus("degraded");
        setQuoteStatusDetail(quote.reason || "Waiting for Market Data...");
        // Soft-fail: keep poller alive; throw so outer backoff engages when no usable price
        if (!hasPrice) {
          throw new Error(quote.reason || "Quote Provider Timeout");
        }
      }
    } catch (requestError) {
      const message =
        requestError instanceof Error ? requestError.message : "Quote request failed";
      const lower = message.toLowerCase();
      let detail = "Reconnecting...";
      if (lower.includes("timeout")) {
        detail = "Quote Provider Timeout";
      } else if (lower.includes("network") || lower.includes("fetch") || lower.includes("failed to fetch")) {
        detail = "Reconnecting...";
      } else if (lower.includes("unavailable") || lower.includes("503") || lower.includes("market data")) {
        detail = "Waiting for Market Data...";
      } else if (message && message.length < 80) {
        detail = message;
      }
      setQuoteFeedStatus("reconnecting");
      setQuoteStatusDetail(detail);
      // Do NOT setIsLivePricing(false) — automatic resume after temporary failures.
      // Do NOT require full dashboard refresh for recovery.
      throw requestError instanceof Error ? requestError : new Error(detail);
    }
  }

  useEffect(() => {
    if (!dashboard) {
      return;
    }

    if (listTab === "positions") {
      void loadPositions(selectedSymbol, true);
    } else if (listTab === "orders") {
      void loadPendingOrders(selectedSymbol, true);
    } else if (listTab === "history") {
      void loadTradeHistory(selectedSymbol, true);
    }
  }, [listTab, selectedSymbol]);

  async function handleExternalPrefill(payload: RecommendationPrefillRequest) {
    setIsBusy(true);
    setError(null);
    try {
      const prefill = await prefillPaperTrade(payload);
      setSelectedSymbol(prefill.symbol);
      setTicket({
        symbol: prefill.symbol,
        side: prefill.side,
        type: prefill.type,
        qty: prefill.qty,
        limitPrice: prefill.limit_price ?? null,
        stopPrice: null,
        stopLoss: prefill.stop_loss ?? null,
        target: prefill.target ?? null,
        notes: prefill.note,
        sourceSignal: String(payload.recommendation_meta.signal ?? "BUY"),
        sourceScore: Number(payload.recommendation_meta.score ?? 0),
        sourceConfidence: Number(payload.recommendation_meta.confidence ?? 0),
      });
      setStatusMessage(`Imported ${prefill.symbol} from scanner recommendation into Paper Trading.`);
      const response = await fetchPaperTradingDashboard(prefill.symbol);
      setDashboard(response);
      onPrefillConsumed?.();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to import recommendation.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handlePlaceOrder() {
    // Centralized pre-check: prevent any API call for BUY when market closed
    if (ticket.side === "BUY") {
      const check = checkCanPlaceBuyOrder();
      if (!check.allowed) {
        showMarketClosedAlert(check);
        setIsBusy(false);
        return;
      }
    }

    setIsBusy(true);
    setError(null);
    setStatusMessage(null);
    try {
      if (editingOrderId) {
        const payload: any = {
          qty: ticket.qty,
          limit_price: ticket.limitPrice,
          stop_price: ticket.stopPrice,
          stop_loss: ticket.stopLoss,
          target: ticket.target,
          type: ticket.type,
          product_type: ticket.productType,
        };
        const response = await updatePaperOrder(editingOrderId, payload as any);
        setStatusMessage(response.message);
        setEditingOrderId(null);
        await loadPositions(ticket.symbol);
      } else {
        const response = await placePaperOrder(ticket, idempotencyKey);
        setStatusMessage(response.message);
        setIdempotencyKey(crypto.randomUUID());
        await Promise.all([
          loadPendingOrders(ticket.symbol),
          loadPositions(ticket.symbol),
          loadTradeHistory(ticket.symbol),
        ]);
        try {
          const acct = await fetchPaperAccountSummary();
          setAccountSummary(acct);
        } catch (e) {
          console.warn('Failed to refresh account after placing order', e);
        }
        // Reset form: keep symbol and current price, clear everything else
        setSelectedSymbol(ticket.symbol);
        setTicket({
          ...DEFAULT_TICKET,
          symbol: ticket.symbol,
          limitPrice: workspace?.current_price ?? null,
          side: ticket.side,
        });
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to place order.");
    } finally {
      setIsBusy(false);
    }
  }

  function handleQuickOrder(side: "BUY" | "SELL", symbol?: string) {
    if (side === "BUY") {
      const check = checkCanPlaceBuyOrder();
      if (!check.allowed) {
        showMarketClosedAlert(check);
        return;
      }
    }
    const normalized = (symbol ?? selectedSymbol ?? ticket.symbol).trim().toUpperCase();
    if (!normalized) return;
    setSelectedSymbol(normalized);
    navigateToPaperOrder(navigate, {
      symbol: normalized,
      side,
      currentPrice: workspace?.current_price ?? null,
      returnTo: "/paper",
    });
  }

  function handleSymbolSelect(symbol: string) {
    const normalizedSymbol = symbol.trim().toUpperCase();
    if (!normalizedSymbol) {
      return;
    }

    const scannerCandidate = scannerCandidateMap.get(normalizedSymbol);
    setSelectedSymbol(normalizedSymbol);
    setTicket((current) =>
      scannerCandidate
        ? buildTicketFromCandidate(scannerCandidate, current, workspace?.current_price ?? null, lastScanAt)
        : {
            ...current,
            symbol: normalizedSymbol,
            limitPrice: workspace?.current_price ?? current.limitPrice ?? null,
          },
    );
    void loadDashboard(normalizedSymbol);
  }

  async function handleReset() {
    setIsBusy(true);
    setError(null);
    try {
      const response = await resetPaperTradingAccount(resetBalance);
      setDashboard(response);
      setStatusMessage(`Paper account reset to ₹${resetBalance.toLocaleString("en-IN")}.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to reset account.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCancelOrder(orderId: number) {
    setIsBusy(true);
    try {
      const response = await cancelPaperOrder(orderId);
      setStatusMessage(response.message);
      await Promise.all([
        loadPendingOrders(selectedSymbol),
        loadPositions(selectedSymbol),
      ]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to cancel order.");
    } finally {
      setIsBusy(false);
    }
  }

  function handleEditOrder(order: PaperOrder) {
    try {
      navigateToPaperOrder(navigate, {
        symbol: order.symbol,
        side: order.side,
        orderId: order.id,
        returnTo: "/paper",
      });
      return;
    } catch {
      setEditingOrderId(order.id);
      setTicket((current) => ({
        ...current,
        symbol: order.symbol,
        side: order.side,
        type: order.type as any,
        productType: order.product_type as any,
        qty: order.qty,
        limitPrice: order.price ?? null,
        stopPrice: order.stop_price ?? null,
        stopLoss: order.stop_loss ?? null,
        target: order.target ?? null,
        notes: order.notes ?? "",
      }));
      setSelectedSymbol(order.symbol);
      setListTab("orders");
    }
  }

  async function handleDeleteOrder(orderId: number) {
    if (!confirm("Cancel this order?")) return;
    setIsBusy(true);
    try {
      const response = await deletePaperOrder(orderId);
      setStatusMessage(response.message);
      await Promise.all([
        loadPendingOrders(selectedSymbol),
        loadPositions(selectedSymbol),
      ]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to cancel order.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleClosePosition(positionId: number) {
    setIsBusy(true);
    try {
      const response = await closePaperPosition(positionId);
      setStatusMessage(response.message);
      await Promise.all([
        loadPositions(selectedSymbol),
        loadPendingOrders(selectedSymbol),
        loadTradeHistory(selectedSymbol),
      ]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to close position.");
    } finally {
      setIsBusy(false);
    }
  }

  function handleExitOpenTicket(position: PaperPosition) {
    setTicket((current) => ({
      ...current,
      symbol: position.symbol,
      side: "SELL",
      type: "MARKET",
      qty: position.qty,
    }));
    setSelectedSymbol(position.symbol);
    setListTab("orders");
    try {
      const el = document.querySelector(".paper-ticket-section") as HTMLElement | null;
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch {
      /* ignore */
    }
  }

  async function handleSquareOffAll() {
    setConfirmAction("square-off");
  }

  async function executeSquareOffAll() {
    setConfirmAction(null);
    setIsBusy(true);
    try {
      const resp = await squareOffAllPositions();
      setDashboard({
        ...resp,
        open_orders: resp.open_orders ?? dashboard?.open_orders ?? [],
        positions: resp.positions ?? [],
        trades: resp.trades ?? dashboard?.trades ?? [],
        order_history: resp.order_history ?? dashboard?.order_history ?? [],
      });
      setStatusMessage("All positions squared off.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to square off all positions.");
    } finally {
      setIsBusy(false);
    }
  }

  async function executeReset() {
    setConfirmAction(null);
    setIsBusy(true);
    setError(null);
    try {
      const response = await resetPaperTradingAccount(resetBalance);
      setDashboard(response);
      setStatusMessage(`Paper account reset to ₹${resetBalance.toLocaleString("en-IN")}.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to reset account.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleStartEngine() {
    setIsBusy(true);
    try {
      const status = await startMarketEngine();
      setEngineStatus(status);
      setStatusMessage("Market engine start requested.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to start market engine.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleStopEngine() {
    setIsBusy(true);
    try {
      const status = await stopMarketEngine();
      setEngineStatus(status);
      setStatusMessage("Market engine stopped.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to stop market engine.");
    } finally {
      setIsBusy(false);
    }
  }

  // Poll unread notifications every 5s and show toasts
  useEffect(() => {
    let mounted = true;
    async function pollNotifications() {
      try {
        const items = await fetchUnreadNotifications();
        if (!mounted || !items || items.length === 0) return;
        const newItems = items.filter((i) => !seenNotifications.current.has(i.id));
        if (newItems.length) {
          // mark as seen locally and schedule removal
          newItems.forEach((n) => {
            seenNotifications.current.add(n.id);
            // Single global toast stack — never a second paper-local banner
            window.dispatchEvent(
              new CustomEvent("app:toast", {
                detail: {
                  level: n.level === "error" ? "error" : n.level === "success" ? "success" : "info",
                  message: n.message,
                  dedupeKey: `paper-notif-${n.id}`,
                },
              }),
            );
          });
          // mark read on server
          await markNotificationsRead(newItems.map((n) => n.id));
        }
      } catch (err) {
        console.warn("Failed to poll notifications", err);
      }
    }
    void pollNotifications();
    const id = window.setInterval(() => void pollNotifications(), 5000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, []);

  async function handleSyncPosition(position: PaperPosition) {
    setIsBusy(true);
    try {
      const response = await updatePaperPosition({
        id: position.id,
        stop_loss: position.stop_loss ?? null,
        target: position.target ?? null,
      });
      setStatusMessage(response.message);
      await loadPositions(selectedSymbol);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to update position.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main className="paper-page">
      <section className="paper-header panel">
        <div>
          <p className="section-label">Paper Desk</p>
          <h1>Practice trading</h1>
          <p className="muted-copy">
            Paper portfolio for Nifty cash stocks — place orders, manage positions, and review performance without real capital.
          </p>
        </div>
        <div className="paper-header-actions">
          {!retailMode ? (
            <>
              <EngineStatusBadge status={engineStatus} />
              <button data-testid="start-market-engine-button" type="button" className="button ghost-button" onClick={() => void handleStartEngine()} disabled={isBusy}>
                Start market feed
              </button>
              <button data-testid="stop-market-engine-button" type="button" className="button ghost-button" onClick={() => void handleStopEngine()} disabled={isBusy}>
                Stop feed
              </button>
            </>
          ) : null}
          {!retailMode ? (
            <label className="inline-field">
              <span>Reset balance</span>
              <input type="number" min={1000} step={1000} value={resetBalance} onChange={(event) => setResetBalance(Number(event.target.value))} />
            </label>
          ) : null}
          <button type="button" className="button ghost-button" onClick={() => void loadDashboard(selectedSymbol)} disabled={isBusy}>
            Refresh
          </button>
          <button
            type="button"
            className="button ghost-button"
            onClick={() => {
              setIsLivePricing((current) => {
                const next = !current;
                if (next) {
                  quoteRetryCountRef.current = 0;
                  setQuoteFeedStatus("connecting");
                  setQuoteStatusDetail("Connecting to Live Market...");
                } else {
                  setQuoteFeedStatus("paused");
                  setQuoteStatusDetail(null);
                }
                return next;
              });
            }}
          >
            {isLivePricing ? "Live price on" : "Live price off"}
          </button>
          <LiveQuoteStatusBadge
            status={isLivePricing ? quoteFeedStatus : "paused"}
            detail={quoteStatusDetail}
            lastQuoteAt={lastQuoteAt}
            lastSuccessfulPrice={lastSuccessfulPrice ?? workspace?.current_price ?? null}
          />
          <button type="button" className="button ghost-button" onClick={() => setConfirmAction("reset")} disabled={isBusy}>
            Reset account
          </button>
        </div>
      </section>

      {/* TRADING WORKSPACE - Positions / Orders / History / Analytics / Daily / Alerts / Capital */}
      <section className="panel paper-tabs-panel">
        <div className="detail-tabs" role="tablist" aria-label="Paper trading data tabs">
          {[
            ["positions", "Positions"],
            ["orders", "Orders"],
            ["history", "History"],
            ["analytics", "Analytics"],
            ["daily-analytics", "Daily"],
            ["alerts", "Alerts"],
            ["account", "Capital"],
            ["watchlist", "Watchlist"],
          ].map(([id, label]) => (
            <button
              key={id}
              data-testid={`paper-tab-${id}`}
              type="button"
              className={`detail-tab ${listTab === id ? "is-active" : ""}`}
              onClick={() => setListTab(id as PaperPanelTab)}
            >
              {label}
            </button>
          ))}
        </div>

        {listTab === "positions" ? (
          <>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8, gap: 8, alignItems: 'center' }}>
              <button type="button" className="button ghost-button" onClick={() => void handleSquareOffAll()} disabled={isBusy || !(dashboard?.positions?.length)}>
                Square Off ALL
              </button>
              <InfoTooltip content={TOOLTIPS.PAPER_TRADING.SQUARE_OFF_ALL} />
            </div>
            {dashboard === null ? (
              <TableSkeleton rows={5} cols={6} />
            ) : (dashboard.positions?.length ?? 0) === 0 ? (
              <div className="ds-empty" role="status">
                <h3 className="ds-empty__title">No open positions</h3>
                <p className="ds-empty__desc">Place a BUY order to open your first paper position.</p>
              </div>
            ) : (
              <PositionsTable
                positions={dashboard.positions}
                selectedSymbol={selectedSymbol}
                onSelect={(symbol) => {
                  setSelectedSymbol(symbol);
                  void loadDashboard(symbol);
                }}
                onClose={(positionId) => void handleClosePosition(positionId)}
                onExit={(position) => handleExitOpenTicket(position)}
              />
            )}
          </>
        ) : null}

        {listTab === "orders" ? (
          dashboard === null ? (
            <TableSkeleton rows={5} cols={6} />
          ) : (dashboard.open_orders?.length ?? 0) === 0 ? (
            <div className="ds-empty" role="status">
              <h3 className="ds-empty__title">No open orders</h3>
              <p className="ds-empty__desc">Use the order ticket to place a limit or market order.</p>
            </div>
          ) : (
            <OrdersTable
              orders={dashboard.open_orders}
              selectedSymbol={selectedSymbol}
              onSelect={(symbol) => {
                setSelectedSymbol(symbol);
                void loadDashboard(symbol);
              }}
              onEdit={(order) => handleEditOrder(order)}
              onDelete={(orderId) => void handleDeleteOrder(orderId)}
            />
          )
        ) : null}

        {listTab === "history" ? (
          dashboard === null ? (
            <TableSkeleton rows={5} cols={6} />
          ) : (dashboard.trades?.length ?? 0) === 0 ? (
            <div className="ds-empty" role="status">
              <h3 className="ds-empty__title">No trade history</h3>
              <p className="ds-empty__desc">Closed trades will appear here after you exit positions.</p>
            </div>
          ) : (
            <HistoryTable trades={dashboard.trades} selectedTrade={selectedTrade} setSelectedTrade={setSelectedTrade} />
          )
        ) : null}

        {listTab === "analytics" ? (
          <Suspense
            fallback={
              <section aria-busy="true">
                <MetricCardSkeleton count={8} />
                <div style={{ display: "flex", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
                  <ChartSkeleton height={200} />
                  <ChartSkeleton height={200} />
                </div>
              </section>
            }
          >
            <AnalyticsPanel />
          </Suspense>
        ) : null}
        {listTab === "daily-analytics" ? (
          <Suspense
            fallback={
              <section className="panel" aria-busy="true">
                <MetricCardSkeleton count={6} />
                <div style={{ marginTop: 12 }}>
                  <ChartSkeleton height={180} />
                </div>
              </section>
            }
          >
            <DailyAnalyticsPanel />
          </Suspense>
        ) : null}
        {listTab === "alerts" ? (
          <AlertsPanel onRefresh={() => void loadPositions(selectedSymbol)} />
        ) : null}
        {listTab === "account" ? (
          <AccountPanel
            onAccountUpdate={(a) => setAccountSummary(a)}
            onDashboardUpdate={(d) => setDashboard(d)}
          />
        ) : null}
        {listTab === "watchlist" ? (
          <WatchlistTab />
        ) : null}
      </section>

      <AccountSummaryStrip dashboard={dashboard} />

      {!retailMode ? (
        <MarketEngineHealthWidget health={engineHealth} lastSuccessfulPoll={lastSuccessfulHealthPoll} errorCount={healthPollErrorCount} />
      ) : null}

      <PaperAccountWidgets
        summary={accountSummary}
        onQuickBuy={(symbol?: string) => handleQuickOrder("BUY", symbol)}
        onQuickSell={(symbol?: string) => handleQuickOrder("SELL", symbol)}
      />

      {confirmAction === "reset" ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="confirm-reset-title" onKeyDown={(e) => { if (e.key === 'Escape') setConfirmAction(null); }} tabIndex={-1}>
          <div className="confirm-modal">
            <h2 id="confirm-reset-title">Reset paper account?</h2>
            <p>This clears positions and orders and restores capital to ₹{resetBalance.toLocaleString("en-IN")}. This cannot be undone.</p>
            {retailMode ? (
              <label className="inline-field" style={{ marginTop: 12 }}>
                <span>Starting capital</span>
                <input type="number" min={1000} step={1000} value={resetBalance} onChange={(event) => setResetBalance(Number(event.target.value))} />
              </label>
            ) : null}
            <div className="modal-actions">
              <button type="button" className="button ghost-button" onClick={() => setConfirmAction(null)}>Cancel</button>
              <button type="button" className="button danger-button" onClick={() => void executeReset()} disabled={isBusy}>Reset account</button>
            </div>
          </div>
        </div>
      ) : null}

      {confirmAction === "square-off" ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="confirm-sqoff-title" onKeyDown={(e) => { if (e.key === 'Escape') setConfirmAction(null); }} tabIndex={-1}>
          <div className="confirm-modal">
            <h2 id="confirm-sqoff-title">Square off all positions?</h2>
            <p>Every open position will be closed at the current market price. This cannot be undone.</p>
            <div className="modal-actions">
              <button type="button" className="button ghost-button" onClick={() => setConfirmAction(null)}>Cancel</button>
              <button type="button" className="button danger-button" onClick={() => void executeSquareOffAll()} disabled={isBusy}>Square off all</button>
            </div>
          </div>
        </div>
      ) : null}

      {/* TRADE DETAILS */}
      <TradeDetailsCard
        position={selectedPosition}
        orders={selectedOrders}
        onPositionChange={(position) => void handleSyncPosition(position)}
      />
    </main>
  );
}

function LiveQuoteStatusBadge({
  status,
  detail,
  lastQuoteAt,
  lastSuccessfulPrice,
}: {
  status: "connecting" | "live" | "reconnecting" | "degraded" | "paused";
  detail: string | null;
  lastQuoteAt: number | null;
  lastSuccessfulPrice: number | null;
}) {
  const labelMap: Record<typeof status, string> = {
    connecting: "Connecting to Live Market...",
    live: "Live Market Connected",
    reconnecting: detail || "Reconnecting...",
    degraded: detail || "Waiting for Market Data...",
    paused: "Live price off",
  };
  const color =
    status === "live"
      ? "#3fb950"
      : status === "reconnecting" || status === "connecting"
        ? "#d29922"
        : status === "degraded"
          ? "#f0883e"
          : "#8b949e";
  const ageSec =
    lastQuoteAt != null ? Math.max(0, Math.round((Date.now() - lastQuoteAt) / 1000)) : null;
  const showSpinner = status === "connecting" || status === "reconnecting";

  return (
    <div
      className="helper-chip"
      data-testid="live-quote-status"
      title={
        lastSuccessfulPrice != null
          ? `Last successful ₹${lastSuccessfulPrice.toFixed(2)}${ageSec != null ? ` · ${ageSec}s ago` : ""}`
          : labelMap[status]
      }
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        borderColor: color,
        color,
        maxWidth: 360,
      }}
    >
      {showSpinner ? (
        <span
          aria-hidden
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            border: `2px solid ${color}`,
            borderTopColor: "transparent",
            animation: "paper-quote-spin 0.8s linear infinite",
            display: "inline-block",
          }}
        />
      ) : (
        <span aria-hidden style={{ fontSize: "0.75rem" }}>
          {status === "live" ? "●" : status === "degraded" ? "◐" : "○"}
        </span>
      )}
      <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {labelMap[status]}
      </span>
      {status !== "live" && lastSuccessfulPrice != null ? (
        <span style={{ opacity: 0.85, whiteSpace: "nowrap" }}>
          · ₹{lastSuccessfulPrice.toFixed(2)}
          {ageSec != null ? ` (${ageSec}s ago)` : ""}
        </span>
      ) : null}
      <style>{`@keyframes paper-quote-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function EngineStatusBadge({ status }: { status: MarketEngineStatus | null }) {
  const label = status?.paused_reason
    ? `${status.status} (${status.paused_reason})`
    : status?.status ?? "UNKNOWN";
  return (
    <div className="helper-chip" title={status?.active_symbols.join(", ") || "No active symbols"}>
      Engine: {label} | Feed: {status?.websocket_connected ? "connected" : "disconnected"} | Symbols: {status?.active_monitored_symbols_count ?? 0}
    </div>
  );
}

function AccountSummaryStrip({ dashboard }: { dashboard: PaperTradingDashboardResponse | null }) {
  if (!dashboard) {
    return (
      <section className="summary-row" aria-busy="true">
        <MetricCardSkeleton count={8} />
      </section>
    );
  }
  const account = dashboard.account;
  const metrics = [
    ["Balance", formatCurrency(account?.balance)],
    ["Equity", formatCurrency(account?.equity)],
    ["Realized P&L", formatCurrency(account?.realized_pnl)],
    ["Unrealized P&L", formatCurrency(account?.unrealized_pnl)],
    ["Invested", formatCurrency(account?.total_invested)],
    ["Available cash", formatCurrency(account?.available_cash)],
    ["Open positions", account?.open_positions_count ?? "--"],
    ["Open orders", account?.open_orders_count ?? "--"],
  ];

  const labelToTooltip: Record<string, string | undefined> = {
    Balance: TOOLTIPS.PAPER_TRADING.BALANCE,
    Equity: TOOLTIPS.PAPER_TRADING.EQUITY,
    "Realized P&L": TOOLTIPS.PAPER_TRADING.REALIZED_PNL,
    "Unrealized P&L": TOOLTIPS.PAPER_TRADING.UNREALIZED_PNL,
    Invested: TOOLTIPS.PAPER_TRADING.INVESTED,
    "Available cash": TOOLTIPS.PAPER_TRADING.AVAILABLE_CASH,
    "Open positions": TOOLTIPS.PAPER_TRADING.OPEN_POSITIONS,
  };

  return (
    <section className="summary-row">
      {metrics.map(([label, value]) => (
        <article key={label as string} className="metric-card">
          <span>
            {label as string}
            {labelToTooltip[label as string] ? <InfoTooltip content={labelToTooltip[label as string] as string} /> : null}
          </span>
          <strong>{value as string}</strong>
          <p>{label === "Available cash" ? "Balance after reserving pending buy orders." : "Paper account metric."}</p>
        </article>
      ))}
    </section>
  );
}

function PaperAccountWidgets({
  summary,
  onQuickBuy,
  onQuickSell,
}: {
  summary: any | null;
  onQuickBuy: (symbol?: string) => void;
  onQuickSell: (symbol?: string) => void;
}) {
  const s = summary ?? {};
  const fmt = (v: number | undefined | null) => (v === undefined || v === null ? "--" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(v));
  const pct = (v: number | undefined | null) => (v === undefined || v === null ? "--" : `${v.toFixed(2)}%`);

  const pnlClass = (v: number | undefined | null) => (v && v > 0 ? "metric-card-positive" : v && v < 0 ? "metric-card-negative" : "");

  return (
    <section className="panel" data-testid="paper-order-ticket">
      <div style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "stretch", flexWrap: "wrap", flex: "1 1 auto" }}>
          <div className="metric-card">
            <span>
              Total capital
            </span>
            <strong>{fmt(s.total_capital)}</strong>
            <p>Virtual account value</p>
          </div>

          <div className="metric-card">
            <span>
              Available funds
              <InfoTooltip content={TOOLTIPS.PAPER_TRADING.AVAILABLE_CASH} />
            </span>
            <strong>{fmt(s.available_funds)}</strong>
            <p>Cash available to place buys</p>
          </div>

          <div className="metric-card">
            <span>Invested value</span>
            <strong>{fmt(s.invested_value)}</strong>
            <p>Sum of open positions</p>
          </div>

          <div className={`metric-card ${pnlClass(s.total_pnl)}`}>
            <span>
              Total P&L
              <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TOTAL_PNL} />
            </span>
            <strong>{fmt(s.total_pnl)}</strong>
            <p>Unrealized + realized</p>
          </div>

          <div className={`metric-card ${pnlClass(s.daily_pnl)}`}>
            <span>
              Daily P&L
              <InfoTooltip content={TOOLTIPS.PAPER_TRADING.DAILY_PNL} />
            </span>
            <strong>{fmt(s.daily_pnl)}</strong>
            <p>{pct(s.daily_pnl_pct)}</p>
          </div>

          <div className="metric-card">
            <span>
              Market status
              <InfoTooltip content={TOOLTIPS.PAPER_TRADING.MARKET_STATUS} />
            </span>
            <strong>{s.market_status ?? "--"}</strong>
            <p>Based on IST clock</p>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="button primary-button" onClick={() => onQuickBuy()}>
            Quick Buy
          </button>
          <button type="button" className="button ghost-button" onClick={() => onQuickSell()}>
            Quick Sell
          </button>
        </div>
      </div>
    </section>
  );
}

function OrderTicketCard({
  symbols,
  scannerSymbols,
  ticket,
  onChange,
  onSymbolSelect,
  onPlace,
  isBusy,
  currentPrice,
  riskMetrics,
  maxRiskPercent,
  availableCash,
  scannerCandidate,
  lastScanAt,
  statusMessage,
  error,
  onDismissStatus,
  onDismissError,
}: {
  symbols: string[];
  scannerSymbols: string[];
  ticket: PaperOrderTicketState;
  onChange: (next: PaperOrderTicketState) => void;
  onSymbolSelect: (symbol: string) => void;
  onPlace: () => void;
  isBusy: boolean;
  currentPrice: number | null;
  riskMetrics: {
    estimatedCost: number;
    riskPerShare: number;
    rewardPerShare: number;
    riskAmount: number;
    riskReward: number;
    riskPercent: number;
    warning: string | null;
  };
  maxRiskPercent: number;
  availableCash: number | null;
  scannerCandidate: CandidateRow | null;
  lastScanAt: string | null;
  statusMessage?: string | null;
  error?: string | null;
  onDismissStatus?: () => void;
  onDismissError?: () => void;
}) {
  const [trailingStopPercent, setTrailingStopPercent] = useState(2);
  const [allocationPercent, setAllocationPercent] = useState(10);
  const [previewOpen, setPreviewOpen] = useState(false);
  const previewRef = useRef<HTMLDivElement>(null);
  const [qtyError, setQtyError] = useState<string | null>(null);
  const LOT_SIZES: Record<string, number> = { "NIFTY-FUT": 50 };
  const scannerSet = useMemo(() => new Set(scannerSymbols), [scannerSymbols]);
  const entryReference =
    ticket.type === "LIMIT" ? ticket.limitPrice : ticket.type === "STOP" ? ticket.stopPrice : currentPrice;
  const suggestedQty =
    availableCash && entryReference && allocationPercent > 0
      ? Math.max(1, Math.floor((availableCash * (allocationPercent / 100)) / entryReference))
      : 1;

  function applyTrailingStop() {
    if (!entryReference || trailingStopPercent <= 0) {
      return;
    }
    const direction = ticket.side === "BUY" ? -1 : 1;
    onChange({
      ...ticket,
      stopLoss: roundPrice(entryReference * (1 + direction * trailingStopPercent / 100)),
      notes: appendTicketNote(ticket.notes, `Trailing stop helper: ${trailingStopPercent}% from entry reference.`),
    });
  }

  function applySuggestedQuantity() {
    onChange({
      ...ticket,
      qty: suggestedQty,
      notes: appendTicketNote(ticket.notes, `Sizing helper: ${allocationPercent}% of available cash.`),
    });
  }

  useEffect(() => {
    if (previewOpen && previewRef.current) {
      previewRef.current.focus();
    }
  }, [previewOpen]);

  useEffect(() => {
    // Lot size validation for futures symbols ending with -FUT
    const sym = (ticket.symbol || "").toUpperCase();
    if (sym.endsWith("-FUT")) {
      const lot = LOT_SIZES[sym] ?? 1;
      if (ticket.qty % lot !== 0) {
        setQtyError(`Qty must be in multiples of ${lot}`);
      } else {
        setQtyError(null);
      }
    } else {
      setQtyError(null);
    }
  }, [ticket.symbol, ticket.qty]);

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="section-label">Order ticket</p>
          <h2>Place paper order</h2>
        </div>
        <span className="helper-chip">Cash only</span>
      </div>

      <div className="paper-ticket-grid">
        <label className="filter-field">
          <span>
            Symbol
            <InfoTooltip content={"Select the stock to trade"} />
          </span>
          <select data-testid="paper-symbol-select" value={ticket.symbol} onChange={(event) => onSymbolSelect(event.target.value)}>
            {symbols.map((symbol) => (
              <option key={symbol} value={symbol}>
                {scannerSet.has(symbol) ? `${symbol} - latest scan` : symbol}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-field">
          <span>
            Side
            <InfoTooltip content={"BUY opens a position, SELL closes an existing position"} />
          </span>
          <select data-testid="paper-side-select" value={ticket.side} onChange={(event) => onChange({ ...ticket, side: event.target.value as "BUY" | "SELL" })}>
            <option value="BUY">Buy</option>
            <option value="SELL">Sell</option>
          </select>
        </label>

        <label className="filter-field">
          <span>
            Order type
            <InfoTooltip content={TOOLTIPS.PAPER_TRADING.ORDER_TYPE} />
          </span>
          <select data-testid="paper-order-type-select" value={ticket.type} onChange={(event) => onChange({ ...ticket, type: event.target.value as any })}>
            <option value="MARKET">Market</option>
            <option value="LIMIT">Limit</option>
            <option value="STOP">Stop-Loss (market on trigger)</option>
            <option value="STOP_LIMIT">Stop-Limit</option>
            <option value="GTT">GTT (Good Till Triggered)</option>
          </select>
        </label>

        <label className="filter-field">
          <span>
            Product
            <InfoTooltip content={TOOLTIPS.PAPER_TRADING.PRODUCT_TYPE} />
          </span>
          <select value={ticket.productType ?? "CNC"} onChange={(event) => onChange({ ...ticket, productType: event.target.value as any })}>
            <option value="MIS">MIS (Intraday)</option>
            <option value="CNC">CNC (Delivery)</option>
            <option value="NRML">NRML (Carry)</option>
          </select>
        </label>

        <label className="filter-field">
          <span>
            Quantity
            <InfoTooltip content={TOOLTIPS.PAPER_TRADING.QUANTITY} />
          </span>
          <input data-testid="paper-qty-input" type="number" min={1} placeholder="1" value={ticket.qty} onChange={(event) => onChange({ ...ticket, qty: Number(event.target.value) })} />
        </label>

        {ticket.type !== "MARKET" ? (
          <label className="filter-field">
            <span>
              {ticket.type === "STOP" || ticket.type === "STOP_LIMIT" ? "Stop trigger" : "Limit price"}
              <InfoTooltip content={ticket.type === "STOP" || ticket.type === "STOP_LIMIT" ? TOOLTIPS.PAPER_TRADING.STOP_LOSS_FIELD : TOOLTIPS.PAPER_TRADING.LIMIT_PRICE} />
            </span>
            <input type="number" min={0.01} step="0.05" placeholder={ticket.type === "LIMIT" ? "Current price" : ""} value={ticket.type === "LIMIT" || ticket.type === "GTT" || ticket.type === "STOP_LIMIT" ? ticket.limitPrice ?? "" : ticket.stopPrice ?? ""} onChange={(event) => onChange({ ...ticket, ...(ticket.type === "LIMIT" || ticket.type === "GTT" || ticket.type === "STOP_LIMIT" ? { limitPrice: Number(event.target.value) || null } : { stopPrice: Number(event.target.value) || null }) })} />
          </label>
        ) : null}

        <label className="filter-field">
          <span>
            Stop-loss
            <InfoTooltip content={TOOLTIPS.PAPER_TRADING.STOP_LOSS_FIELD} />
          </span>
          <input type="number" min={0.01} step="0.05" placeholder="Auto-calculated" value={ticket.stopLoss ?? ""} onChange={(event) => onChange({ ...ticket, stopLoss: Number(event.target.value) || null })} />
        </label>

        <label className="filter-field">
          <span>
            Target
            <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TARGET_FIELD} />
          </span>
          <input type="number" min={0.01} step="0.05" placeholder="Auto-calculated" value={ticket.target ?? ""} onChange={(event) => onChange({ ...ticket, target: Number(event.target.value) || null })} />
        </label>
      </div>

      <label className="filter-field">
        <span>Notes</span>
        <input value={ticket.notes ?? ""} onChange={(event) => onChange({ ...ticket, notes: event.target.value })} />
      </label>

      <div className="broker-helper-grid">
        <label className="filter-field">
          <span>
            Trailing stop %
            <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TRAILING_STOP} />
          </span>
          <input type="number" min={0.1} step="0.1" placeholder="2" value={trailingStopPercent} onChange={(event) => setTrailingStopPercent(Number(event.target.value) || 0)} />
        </label>
        <label className="filter-field">
          <span>
            Cash allocation %
            <InfoTooltip content={TOOLTIPS.PAPER_TRADING.CASH_ALLOCATION} />
          </span>
          <input type="number" min={1} max={100} step="1" placeholder="10" value={allocationPercent} onChange={(event) => setAllocationPercent(Number(event.target.value) || 0)} />
        </label>
        <button type="button" className="button ghost-button" onClick={applyTrailingStop}>
          Apply trailing SL
        </button>
        <button type="button" className="button ghost-button" onClick={applySuggestedQuantity}>
          Use suggested qty {suggestedQty}
          <InfoTooltip content={TOOLTIPS.PAPER_TRADING.SUGGESTED_QTY} />
        </button>
      </div>

      {scannerCandidate ? (
        <div className="scan-prefill-box">
          <div>
            <strong>{scannerCandidate.signal} from latest scanner</strong>
            <p>{scannerCandidate.recommendationSummary}</p>
          </div>
          <div className="scan-prefill-metrics">
            <Metric label="Score" value={scannerCandidate.score === null || scannerCandidate.score === undefined ? "N/A" : scannerCandidate.score.toFixed(1)} />
            <Metric label="Confidence" value={scannerCandidate.confidence === null ? "--" : `${Math.round(scannerCandidate.confidence * 100)}%`} />
            <Metric label="RR" value={scannerCandidate.riskReward?.toFixed(2) ?? "--"} />
            <Metric label="Scan time" value={lastScanAt ? new Date(lastScanAt).toLocaleTimeString() : "--"} />
          </div>
        </div>
      ) : null}

      <div className="score-breakdown">
        <Metric label="Current" value={currentPrice ? `₹${currentPrice.toFixed(2)}` : "--"} />
        <Metric label="Estimated cost" value={formatCurrency(riskMetrics.estimatedCost)} />
        <Metric label="Risk amount" value={formatCurrency(riskMetrics.riskAmount)} />
        <Metric label="Risk / Reward" value={riskMetrics.riskReward ? riskMetrics.riskReward.toFixed(2) : "--"} />
      </div>

      <p className="helper-text">
        Account rule: avoid risking more than {(maxRiskPercent * 100).toFixed(1)}% per trade and prefer setups with at least 1:2 risk-reward.
      </p>
      {riskMetrics.warning ? <div className="warning-box"><strong>Risk warning</strong><p>{riskMetrics.warning}</p></div> : null}

      <div className="paper-ticket-footer">
        <span className="helper-chip">Risk {riskMetrics.riskPercent.toFixed(2)}% of account</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {qtyError ? <div className="error-state" style={{ display: 'inline-block', padding: 8 }}>{qtyError}</div> : null}
          {statusMessage ? (
            <PaperToast type="success" onDismiss={onDismissStatus ?? (() => {})}>
              {statusMessage}
            </PaperToast>
          ) : null}
          {error ? (
            <PaperToast type="error" onDismiss={onDismissError ?? (() => {})}>
              {error}
            </PaperToast>
          ) : null}
          <button data-testid="paper-place-order-button" type="button" className="button primary-button" onClick={() => setPreviewOpen(true)} disabled={isBusy || !!qtyError || (ticket.side === "BUY" && !checkCanPlaceBuyOrder().allowed)}>
            {isBusy ? "Working..." : "Place paper order"}
          </button>
        </div>
      </div>
      {previewOpen ? (
        <div
          ref={previewRef}
          className="panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="order-preview-title"
          tabIndex={-1}
          style={{ position: 'fixed', left: '50%', top: '20%', transform: 'translateX(-50%)', zIndex: 60, width: "95%", maxWidth: 520 }}
          onKeyDown={(e) => { if (e.key === 'Escape') setPreviewOpen(false); }}
        >
          <div className="panel-header">
            <div>
              <p className="section-label">Order preview</p>
              <h2 id="order-preview-title">Confirm order</h2>
            </div>
          </div>
          <div style={{ padding: 12 }}>
            <p>
              You are {ticket.side === 'BUY' ? 'buying' : 'selling'} {ticket.qty} {ticket.symbol} at ₹{(entryReference ?? 0).toFixed(2)}
            </p>
            <p>Brokerage: ₹0 (paper trade)</p>
            <p>
              STT: ₹0.1% on sell side = ₹{(ticket.side === 'SELL' ? ((entryReference ?? 0) * ticket.qty * 0.001).toFixed(2) : '0.00')}
            </p>
            <p>
              Total estimated charges: ₹{(ticket.side === 'SELL' ? ((entryReference ?? 0) * ticket.qty * 0.001).toFixed(2) : '0.00')}
            </p>
            <p>
              Estimated total {ticket.side === 'BUY' ? 'cost' : 'proceeds'}: ₹{ticket.side === 'BUY' ? ((entryReference ?? 0) * ticket.qty + 0).toFixed(2) : ((entryReference ?? 0) * ticket.qty - ((entryReference ?? 0) * ticket.qty * 0.001)).toFixed(2)}
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
              <button type="button" className="button ghost-button" onClick={() => setPreviewOpen(false)}>Cancel</button>
              <button data-testid="paper-confirm-order-button" type="button" className="button primary-button" onClick={async () => { setPreviewOpen(false); await onPlace(); }}>
                Confirm
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PositionCard({ position, selectedSymbol, onSelect, onClose, onExit }: {
  position: PaperPosition;
  selectedSymbol: string;
  onSelect: (symbol: string) => void;
  onClose: (positionId: number) => void;
  onExit: (position: PaperPosition) => void;
}) {
  return (
    <div className={`paper-card ${selectedSymbol === position.symbol ? "is-selected" : ""}`}>
      <div className="paper-card__header">
        <button type="button" className="paper-card__symbol" onClick={() => onSelect(position.symbol)}>{position.symbol}</button>
        <span className={`paper-card__status ${position.unrealized_pnl >= 0 ? "paper-card__pnl-positive" : "paper-card__pnl-negative"}`}>
          {formatCurrency(position.unrealized_pnl)} ({position.unrealized_pnl_percent.toFixed(2)}%)
        </span>
      </div>
      <div className="paper-card__body">
        <div className="paper-card__field"><span className="paper-card__field-label">Qty</span><span className="paper-card__field-value">{position.qty}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Avg</span><span className="paper-card__field-value">{position.avg_entry_price.toFixed(2)}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Current</span><span className="paper-card__field-value">{position.current_price?.toFixed(2) ?? "--"}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Stop</span><span className="paper-card__field-value">{position.stop_loss?.toFixed(2) ?? "--"}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Target</span><span className="paper-card__field-value">{position.target?.toFixed(2) ?? "--"}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">R:R</span><span className="paper-card__field-value">{position.risk_reward_ratio?.toFixed(2) ?? "--"}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Status</span><span className="paper-card__field-value">{formatLifecycle(position.lifecycle_state, position.paused_reason)}</span></div>
      </div>
      <div className="paper-card__actions">
        <button type="button" className="button ghost-button" onClick={() => onExit(position)}>Exit</button>
        <button type="button" className="button ghost-button" onClick={() => onClose(position.id)}>Square Off</button>
      </div>
    </div>
  );
}

const PositionsTable = memo(function PositionsTable({
  positions,
  selectedSymbol,
  onSelect,
  onClose,
  onExit,
}: {
  positions: PaperPosition[];
  selectedSymbol: string;
  onSelect: (symbol: string) => void;
  onClose: (positionId: number) => void;
  onExit: (position: PaperPosition) => void;
}) {
  if (!positions.length) {
    return <div className="empty-state"><h2>No open positions</h2><p>Use the order ticket to create a simulated swing position.</p></div>;
  }

  return (
    <>
      <div className="table-scroll paper-data-table">
        <table className="candidate-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Qty</th>
            <th>Avg entry <InfoTooltip content={TOOLTIPS.PAPER_TRADING.AVG_ENTRY} /></th>
            <th>Current <InfoTooltip content={TOOLTIPS.PAPER_TRADING.CURRENT_PRICE} /></th>
            <th>Unrealized <InfoTooltip content={TOOLTIPS.PAPER_TRADING.UNREALIZED_COL} /></th>
            <th>% P&L <InfoTooltip content={TOOLTIPS.PAPER_TRADING.PERCENT_PNL} /></th>
            <th>Stop <InfoTooltip content={TOOLTIPS.PAPER_TRADING.STOP_COL} /></th>
            <th>Target <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TARGET_COL} /></th>
            <th>R:R <InfoTooltip content={TOOLTIPS.PAPER_TRADING.RR_COL} /></th>
            <th>Monitoring</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr key={position.id} className={selectedSymbol === position.symbol ? "is-selected" : ""} data-testid="position-row">
              <td><button type="button" className="text-button" onClick={() => onSelect(position.symbol)}>{position.symbol}</button></td>
              <td>{position.qty}</td>
              <td className="number-cell">{position.avg_entry_price.toFixed(2)}</td>
              <td className="number-cell">{position.current_price?.toFixed(2) ?? "--"}</td>
              <td className={`number-cell ${position.unrealized_pnl >= 0 ? "text-positive" : "text-negative"}`}>{formatCurrency(position.unrealized_pnl)}</td>
              <td className={`number-cell ${position.unrealized_pnl_percent >= 0 ? "text-positive" : "text-negative"}`}>{position.unrealized_pnl_percent.toFixed(2)}%</td>
              <td className="number-cell">{position.stop_loss?.toFixed(2) ?? "--"}</td>
              <td className="number-cell">{position.target?.toFixed(2) ?? "--"}</td>
              <td className="number-cell">{position.risk_reward_ratio?.toFixed(2) ?? "--"}</td>
              <td>{formatLifecycle(position.lifecycle_state, position.paused_reason)}</td>
              <td style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="button ghost-button small-button" onClick={() => onExit(position)}>Exit</button>
                <button type="button" className="button ghost-button small-button" onClick={() => onClose(position.id)}>Square Off</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      <div className="paper-cards">
        {positions.map((position) => (
          <PositionCard key={position.id} position={position} selectedSymbol={selectedSymbol} onSelect={onSelect} onClose={onClose} onExit={onExit} />
        ))}
      </div>
    </>
  );
});

function OrderCard({ order, selectedSymbol, onSelect, onEdit, onDelete }: {
  order: PaperOrder;
  selectedSymbol: string;
  onSelect: (symbol: string) => void;
  onEdit: (order: PaperOrder) => void;
  onDelete: (orderId: number) => void;
}) {
  return (
    <div className={`paper-card ${selectedSymbol === order.symbol ? "is-selected" : ""}`}>
      <div className="paper-card__header">
        <button type="button" className="paper-card__symbol" onClick={() => onSelect(order.symbol)}>{order.symbol}</button>
        <span className={`status-tag ${order.status === "PENDING" ? "is-neutral" : order.status === "FILLED" ? "is-positive" : "is-risk"}`}>{order.status}</span>
      </div>
      <div className="paper-card__body">
        <div className="paper-card__field"><span className="paper-card__field-label">Side</span><span className="paper-card__field-value">{order.side}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Type</span><span className="paper-card__field-value">{order.type}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Qty</span><span className="paper-card__field-value">{order.qty}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Price</span><span className="paper-card__field-value">{order.price?.toFixed(2) ?? "--"}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Lifecycle</span><span className="paper-card__field-value">{formatLifecycle(order.lifecycle_state, order.paused_reason)}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Placed</span><span className="paper-card__field-value">{new Date(order.created_at).toLocaleString()}</span></div>
      </div>
      <div className="paper-card__actions">
        <button type="button" className="button ghost-button" onClick={() => onEdit(order)}>Edit</button>
        <button type="button" className="button ghost-button" onClick={() => onDelete(order.id)}>Cancel</button>
      </div>
    </div>
  );
}

const OrdersTable = memo(function OrdersTable({
  orders,
  selectedSymbol,
  onSelect,
  onEdit,
  onDelete,
}: {
  orders: PaperOrder[];
  selectedSymbol: string;
  onSelect: (symbol: string) => void;
  onEdit: (order: PaperOrder) => void;
  onDelete: (orderId: number) => void;
}) {
  if (!orders.length) {
    return <div className="empty-state"><h2>No pending orders</h2><p>Limit and stop orders will stay here until your simulated trigger is reached.</p></div>;
  }

  return (
    <>
      <div className="table-scroll paper-data-table">
        <table className="candidate-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Order price</th>
              <th>Placed</th>
              <th>Status</th>
              <th>Lifecycle</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id} className={selectedSymbol === order.symbol ? "is-selected" : ""}>
                <td><button type="button" className="text-button" onClick={() => onSelect(order.symbol)}>{order.symbol}</button></td>
                <td>{order.side}</td>
                <td>{order.type}</td>
                <td>{order.qty}</td>
                <td className="number-cell">{order.price?.toFixed(2) ?? "--"}</td>
                <td>{new Date(order.created_at).toLocaleString()}</td>
                <td><span className={`status-tag ${order.status === "PENDING" ? "is-neutral" : order.status === "FILLED" ? "is-positive" : "is-risk"}`}>{order.status}</span></td>
                <td>{formatLifecycle(order.lifecycle_state, order.paused_reason)}</td>
                <td style={{ display: 'flex', gap: 8 }}>
                  <button type="button" className="button ghost-button small-button" onClick={() => onEdit(order)}>Edit</button>
                  <button type="button" className="button ghost-button small-button" onClick={() => onDelete(order.id)}>Cancel</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="paper-cards">
        {orders.map((order) => (
          <OrderCard key={order.id} order={order} selectedSymbol={selectedSymbol} onSelect={onSelect} onEdit={onEdit} onDelete={onDelete} />
        ))}
      </div>
    </>
  );
});

function formatLifecycle(state?: string | null, pausedReason?: string | null) {
  if (!state) return "--";
  if (pausedReason) return `${state} (${pausedReason})`;
  return state.replace(/_/g, " ");
}

function HistoryCard({ trade, onSelect }: { trade: PaperTradeHistoryItem; onSelect: (t: PaperTradeHistoryItem) => void }) {
  return (
    <div className="paper-card" onClick={() => onSelect(trade)} style={{ cursor: 'pointer' }}>
      <div className="paper-card__header">
        <span className="paper-card__symbol" style={{ color: 'var(--text)', cursor: 'pointer' }}>{trade.symbol}</span>
        <span className={`paper-card__status ${trade.pnl >= 0 ? "paper-card__pnl-positive" : "paper-card__pnl-negative"}`}>
          {formatCurrency(trade.pnl)} ({trade.pnl_percent.toFixed(2)}%)
        </span>
      </div>
      <div className="paper-card__body">
        <div className="paper-card__field"><span className="paper-card__field-label">Qty</span><span className="paper-card__field-value">{trade.qty}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Entry</span><span className="paper-card__field-value">{trade.entry_price.toFixed(2)}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Exit</span><span className="paper-card__field-value">{trade.exit_price.toFixed(2)}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Hold</span><span className="paper-card__field-value">{trade.holding_period_hours.toFixed(1)}h</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Exit Reason</span><span className="paper-card__field-value">{trade.exit_reason ?? "MANUAL"}</span></div>
        <div className="paper-card__field"><span className="paper-card__field-label">Closed</span><span className="paper-card__field-value">{new Date(trade.closed_at).toLocaleString()}</span></div>
      </div>
    </div>
  );
}

const HistoryTable = memo(function HistoryTable({ trades, selectedTrade, setSelectedTrade }: { trades: PaperTradeHistoryItem[]; selectedTrade: PaperTradeHistoryItem | null; setSelectedTrade: (t: PaperTradeHistoryItem | null) => void }) {
  if (!trades.length) {
    return <div className="empty-state"><h2>No trade history</h2><p>Closed paper trades will appear here with holding period and P&amp;L.</p></div>;
  }

  return (
    <>
      <div className="table-scroll paper-data-table">
        <table className="candidate-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Qty</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>P&amp;L</th>
              <th>P&amp;L %</th>
              <th>Signal</th>
              <th>Score</th>
              <th>Opened</th>
              <th>Closed</th>
              <th>Exit Reason</th>
              <th>Hold</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => (
              <tr key={trade.id} data-testid="history-row" onClick={() => setSelectedTrade(trade)} style={{ cursor: 'pointer' }}>
                <td>{trade.symbol}</td>
                <td>{trade.qty}</td>
                <td className="number-cell">{trade.entry_price.toFixed(2)}</td>
                <td className="number-cell">{trade.exit_price.toFixed(2)}</td>
                <td className={`number-cell ${trade.pnl >= 0 ? "text-positive" : "text-negative"}`}>{formatCurrency(trade.pnl)}</td>
                <td className={`number-cell ${trade.pnl >= 0 ? "text-positive" : "text-negative"}`}>{trade.pnl_percent.toFixed(2)}%</td>
                <td>{trade.source_signal ? <span className={`signal-badge signal-${trade.source_signal.toLowerCase()}`}>{trade.source_signal}</span> : "--"}</td>
                <td className="number-cell">{trade.source_score?.toFixed(1) ?? "--"}</td>
                <td>{new Date(trade.opened_at).toLocaleString()}</td>
                <td>{new Date(trade.closed_at).toLocaleString()}</td>
                <td>{trade.exit_reason ?? "MANUAL"}</td>
                <td>{trade.holding_period_hours.toFixed(1)}h</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="paper-cards">
        {trades.map((trade) => (
          <HistoryCard key={trade.id} trade={trade} onSelect={setSelectedTrade} />
        ))}
      </div>
      <TradeDetailsModal trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
    </>
  );
});


function AlertsPanel({ onRefresh }: { onRefresh?: () => void }) {
  const [loading, setLoading] = useState(() => !getCached(CACHE_KEYS.paperAlerts));
  const [symbol, setSymbol] = useState("");
  const [condition, setCondition] = useState<"<=" | ">=">(">=");
  const [price, setPrice] = useState<number | "">("");
  const [alerts, setAlerts] = useState<any[]>(() => getCached(CACHE_KEYS.paperAlerts) || []);
  const [error, setError] = useState<string | null>(null);

  async function load(force = false) {
    if (!alerts.length) setLoading(true);
    try {
      const data = await fetchAlerts({ force });
      setAlerts(data || []);
    } catch (e: any) {
      if (!alerts.length) setError(String(e?.message ?? e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreate() {
    setError(null);
    if (!symbol || !price) {
      setError("Symbol and price are required");
      return;
    }
    try {
      await createAlert({ symbol, condition, price: Number(price) });
      setSymbol("");
      setPrice("");
      await load();
      onRefresh?.();
    } catch (e: any) {
      setError(String(e?.message ?? e));
    }
  }

  async function handleDelete(id: number) {
    if (!confirm("Delete this alert?")) return;
    try {
      await deleteAlert(id);
      await load();
      onRefresh?.();
    } catch (e: any) {
      setError(String(e?.message ?? e));
    }
  }

  // Always render create form; skeleton only for list when empty+loading
  return (
    <section>
      <div className="panel">
        <div className="panel-header"><div><p className="section-label">Price alerts</p><h2>Create alert</h2></div></div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <label style={{ display: 'flex', flexDirection: 'column' }}>
            <span>
              Symbol
              <InfoTooltip content={TOOLTIPS.ALERTS.SYMBOL_FIELD} />
            </span>
            <input placeholder="RELIANCE-EQ" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} style={{ width: 140 }} />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column' }}>
            <span>
              Condition
              <InfoTooltip content={TOOLTIPS.ALERTS.CONDITION} />
            </span>
            <select value={condition} onChange={(e) => setCondition(e.target.value as any)}>
              <option value=">=">Price ≥</option>
              <option value="<=">Price ≤</option>
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column' }}>
            <span>
              Price
              <InfoTooltip content={TOOLTIPS.ALERTS.TARGET_PRICE} />
            </span>
            <input type="number" placeholder="2500.00" value={price} onChange={(e) => setPrice(e.target.value === '' ? '' : Number(e.target.value))} style={{ width: 140 }} />
          </label>
          <div>
            <button className="button primary-button" onClick={() => void handleCreate()}>
              Set Alert
            </button>
            <InfoTooltip content={TOOLTIPS.ALERTS.CREATE_ALERT} />
          </div>
        </div>
        {error ? <div className="error-state" style={{ marginTop: 8 }}>{error}</div> : null}
      </div>

      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Active alerts</p><h2>Alerts</h2></div></div>
        {loading && alerts.length === 0 ? (
          <TableSkeleton rows={3} cols={5} />
        ) : (
          <div className="table-scroll">
            <table className="candidate-table">
              <thead><tr><th>Symbol</th><th>Condition</th><th>Target</th><th>Status</th><th>Created</th><th></th></tr></thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id}><td>{a.symbol}</td><td>{a.condition}</td><td className="number-cell">₹{Number(a.target_price).toFixed(2)}</td><td>{a.status}</td><td>{new Date(a.created_at).toLocaleString()}</td><td><button className="button ghost-button" onClick={() => void handleDelete(a.id)}>Delete</button></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}

function AccountPanel({
  onAccountUpdate,
  onDashboardUpdate,
}: {
  onAccountUpdate?: (d: any) => void;
  onDashboardUpdate?: (d: any) => void;
  /** @deprecated Token panel is always shown on Capital; kept for call-site compatibility */
  hideOps?: boolean;
}) {
  const [account, setAccount] = useState<any | null>(() => getCached(CACHE_KEYS.paperAccount));
  const [loading, setLoading] = useState(() => !getCached(CACHE_KEYS.paperAccount));
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState<number>(() => {
    const cached = getCached<any>(CACHE_KEYS.paperAccount);
    return cached?.starting_balance ?? 1000000;
  });
  const [page, setPage] = useState<number>(1);
  const [transactions, setTransactions] = useState<any | null>(null);
  const [localMessage, setLocalMessage] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const perPage = 20;

  useEffect(() => {
    let mounted = true;
    async function load() {
      if (!account) setLoading(true);
      try {
        // Parallel: account + first page of transactions
        const [acct, tx] = await Promise.all([
          fetchPaperAccountSummary(),
          fetchPaperAccountTransactions(1, perPage).catch(() => null),
        ]);
        if (!mounted) return;
        if (acct) {
          setAccount(acct);
          setStarting(acct.starting_balance ?? 1000000);
        }
        if (tx) setTransactions(tx);
      } catch (e) {
        console.warn("Failed to load account summary", e);
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (page === 1 && transactions) return; // already loaded in parallel mount
    void loadTransactions(page);
  }, [page]);

  async function loadTransactions(p: number) {
    try {
      const data = await fetchPaperAccountTransactions(p, perPage);
      setTransactions(data);
    } catch (e) {
      console.warn("Failed to load transactions", e);
    }
  }

  async function handleSaveStarting() {
    setSaving(true);
    try {
      const resp = await updatePaperAccountCapital(Number(starting));
      if (resp?.account) {
        setAccount(resp.account);
        onAccountUpdate?.(resp.account);
      }
      console.info("Starting capital updated.");
    } catch (e: any) {
      console.error(String(e?.message ?? e));
    } finally {
      setSaving(false);
    }
  }

  async function handleResetAccount() {
    const ok = window.confirm("Reset account: this will close all positions, cancel orders, reset capital and clear history. Continue?");
    if (!ok) return;
    setBusy(true);
    try {
      const resp = await resetPaperTradingAccount(Number(starting));
      setAccount((resp as any).account ?? null);
      onAccountUpdate?.((resp as any).account ?? null);
      onDashboardUpdate?.(resp as any);
      setLocalMessage("Account reset completed.");
      setTimeout(() => setLocalMessage(null), 3000);
      // reload transactions
      void loadTransactions(1);
    } catch (e: any) {
      setLocalError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Account Summary</p><h2>Summary</h2></div></div>
        {loading && !account ? (
          <MetricCardSkeleton count={6} />
        ) : (
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <div className="metric-card"><span>Starting Capital</span><strong>₹{(account?.starting_balance ?? starting).toLocaleString()}</strong></div>
            <div className="metric-card"><span>Current Total Capital</span><strong data-testid="account-balance">₹{((account?.starting_balance ?? 0) + (account?.realized_pnl ?? 0)).toFixed(2)}</strong></div>
            <div className="metric-card"><span>Available Funds</span><strong>₹{(account?.available_cash ?? 0).toFixed(2)}</strong></div>
            <div className="metric-card"><span>Margin Used</span><strong>₹{(account?.total_invested ?? 0).toFixed(2)}</strong></div>
            <div className="metric-card"><span>Total Realized P&L</span><strong>₹{(account?.realized_pnl ?? 0).toFixed(2)}</strong></div>
            <div className="metric-card"><span>Total Unrealized P&L</span><strong>₹{(account?.unrealized_pnl ?? 0).toFixed(2)}</strong></div>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Configuration</p><h2>Account Settings</h2></div></div>
        <div className="capital-settings-row">
          <label className="capital-settings-field">
            Set Starting Capital
            <input type="number" value={starting} onChange={(e) => setStarting(Number(e.target.value || 0))} />
          </label>
          <div className="capital-settings-actions">
            <button className="button" onClick={() => void handleSaveStarting()} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
            <button className="button ghost-button" onClick={() => void handleResetAccount()} disabled={busy}>Reset Account</button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Transaction Log</p><h2>Transactions</h2></div></div>
        <div className="table-scroll">
          <table className="candidate-table">
            <thead>
              <tr><th>DateTime</th><th>Symbol</th><th>Action</th><th>Amount</th><th>Balance After</th></tr>
            </thead>
            <tbody>
              {(transactions?.items ?? []).map((row: any) => (
                <tr key={row.id}><td>{new Date(row.timestamp).toLocaleString()}</td><td>{row.symbol}</td><td>{row.action}</td><td className="number-cell">{row.amount >= 0 ? `₹${row.amount.toFixed(2)}` : `-₹${Math.abs(row.amount).toFixed(2)}`}</td><td className="number-cell">{row.balance_after != null ? `₹${row.balance_after.toFixed(2)}` : '-'}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
          <div>Showing {transactions ? transactions.items.length : 0} of {transactions?.total ?? 0}</div>
          <div>
            <button className="button ghost-button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>Prev</button>
            <span style={{ margin: '0 8px' }}>Page {page} / {transactions?.total_pages ?? 1}</span>
            <button className="button ghost-button" onClick={() => setPage((p) => p + 1)} disabled={page >= (transactions?.total_pages ?? 1)}>Next</button>
          </div>
        </div>
      </section>

      {/* Paper Desk → Capital → Token Management */}
      <TokenStatus embedded />
    </section>
  );
}

function TradeDetailsCard({
  position,
  orders,
  onPositionChange,
}: {
  position: PaperPosition | null;
  orders: PaperOrder[];
  onPositionChange: (position: PaperPosition) => void;
}) {
  const [draftStop, setDraftStop] = useState<number | "">("");
  const [draftTarget, setDraftTarget] = useState<number | "">("");

  useEffect(() => {
    setDraftStop(position?.stop_loss ?? "");
    setDraftTarget(position?.target ?? "");
  }, [position?.id]);

  if (!position) {
    return (
      <section className="panel empty-state">
        <h2>No position selected</h2>
        <p>Select a symbol with an active position to adjust stop-loss or target in the trade details panel.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="section-label">Trade details</p>
          <h2>{position.symbol}</h2>
        </div>
        {position.source_signal ? <span className={`signal-badge signal-${position.source_signal.toLowerCase()}`}>{position.source_signal}</span> : null}
      </div>
      <div className="score-breakdown">
        <Metric label="Entry" value={position.avg_entry_price.toFixed(2)} />
        <Metric label="Current" value={position.current_price?.toFixed(2) ?? "--"} />
        <Metric label="Unrealized" value={formatCurrency(position.unrealized_pnl)} />
        <Metric label="Position size" value={position.qty} />
      </div>

      <div className="paper-ticket-grid">
        <label className="filter-field">
          <span>Stop-loss</span>
          <input type="number" min={0.01} step="0.05" value={draftStop} onChange={(event) => setDraftStop(event.target.value === "" ? "" : Number(event.target.value))} />
        </label>
        <label className="filter-field">
          <span>Target</span>
          <input type="number" min={0.01} step="0.05" value={draftTarget} onChange={(event) => setDraftTarget(event.target.value === "" ? "" : Number(event.target.value))} />
        </label>
      </div>

      <div className="paper-ticket-footer">
        <span className="helper-chip">{orders.length} pending order(s) linked to this symbol</span>
        <button
          type="button"
          className="button primary-button"
          onClick={() =>
            onPositionChange({
              ...position,
              stop_loss: draftStop === "" ? null : draftStop,
              target: draftTarget === "" ? null : draftTarget,
            })
          }
        >
          Update SL / TP
        </button>
      </div>
    </section>
  );
}

function PaperChart({
  workspace,
  ticket,
}: {
  workspace: PaperTradingDashboardResponse["selected_workspace"] | null;
  ticket: PaperOrderTicketState;
}) {
  if (!workspace?.candles.length) {
    return <div className="empty-state"><h2>No chart data</h2><p>Select a symbol or refresh the workspace to load candles.</p></div>;
  }

  const candles = workspace.candles.slice(-40);
  const width = 920;
  const height = 320;
  const volumeHeight = 54;
  const chartHeight = height - volumeHeight - 24;
  const prices = candles.flatMap((candle) => [candle.high, candle.low]);
  const minPrice = Math.min(...prices) * 0.995;
  const maxPrice = Math.max(...prices) * 1.005;
  const maxVolume = Math.max(...candles.map((candle) => candle.volume), 1);
  const candleWidth = Math.max(5, width / (candles.length * 1.9));
  const xFor = (index: number) => 30 + (index * (width - 60)) / Math.max(candles.length - 1, 1);
  const yFor = (price: number) => 18 + ((maxPrice - price) / (maxPrice - minPrice)) * chartHeight;
  const emaLine = workspace.ema_20
    ? buildGuidePath(candles, workspace.ema_20, xFor, yFor)
    : "";
  const supertrendLine = workspace.supertrend
    ? buildGuidePath(candles, workspace.supertrend, xFor, yFor)
    : "";
  const levels = [
    { label: "Entry", value: ticket.type === "LIMIT" ? ticket.limitPrice : workspace.current_price, className: "chart-line-entry" },
    { label: "Stop", value: ticket.stopLoss, className: "chart-line-stop" },
    { label: "Target", value: ticket.target, className: "chart-line-target" },
  ].filter((item) => item.value);

  return (
    <div className="chart-shell">
      <svg viewBox={`0 0 ${width} ${height}`} className="price-chart" role="img" aria-label="Paper trading chart">
        {levels.map((level) => {
          const y = yFor(Number(level.value));
          return (
            <g key={`${level.label}-${level.value}`}>
              <line x1="20" y1={y} x2={width - 20} y2={y} className={level.className} />
              <text x={width - 14} y={y - 4} className="chart-label">{level.label} {Number(level.value).toFixed(2)}</text>
            </g>
          );
        })}
        {emaLine ? <path d={emaLine} className="chart-line-ema" /> : null}
        {supertrendLine ? <path d={supertrendLine} className="chart-line-supertrend" /> : null}
        {candles.map((candle, index) => {
          const x = xFor(index);
          const highY = yFor(candle.high);
          const lowY = yFor(candle.low);
          const openY = yFor(candle.open);
          const closeY = yFor(candle.close);
          const isUp = candle.close >= candle.open;
          const bodyTop = Math.min(openY, closeY);
          const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
          const volumeBarHeight = (candle.volume / maxVolume) * volumeHeight;
          return (
            <g key={`${candle.timestamp}-${index}`}>
              <line x1={x} x2={x} y1={highY} y2={lowY} className={isUp ? "candle-wick-up" : "candle-wick-down"} />
              <rect x={x - candleWidth / 2} y={bodyTop} width={candleWidth} height={bodyHeight} className={isUp ? "candle-body-up" : "candle-body-down"} rx="1" />
              <rect x={x - candleWidth / 2} y={height - volumeBarHeight - 10} width={candleWidth} height={volumeBarHeight} className="volume-bar" rx="1" />
            </g>
          );
        })}
      </svg>
      <div className="chart-legend">
        <span><i className="legend-swatch legend-ema" /> EMA 20</span>
        <span><i className="legend-swatch legend-supertrend" /> Supertrend</span>
        <span><i className="legend-swatch legend-entry" /> Entry / SL / Target</span>
      </div>
    </div>
  );
}

function PaperToast({ type, children, onDismiss }: { type: "success" | "error"; children: React.ReactNode; onDismiss: () => void }) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setVisible(false);
      onDismiss();
    }, 4000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  if (!visible) return null;

  return (
    <div className={`local-toast local-toast--${type}`} role={type === "error" ? "alert" : "status"} style={{ margin: 0, whiteSpace: 'nowrap' }}>
      <span className="local-toast__icon">{type === "success" ? "✓" : "!"}</span>
      <span>{children}</span>
      <button
        type="button"
        onClick={() => { setVisible(false); onDismiss(); }}
        style={{ background: 'none', border: 'none', color: 'inherit', padding: '2px 4px', cursor: 'pointer', fontSize: '1rem', lineHeight: 1, opacity: 0.7 }}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatCurrency(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "--";
  }
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function uniqueSymbols(symbols: string[]) {
  return Array.from(new Set(symbols.filter(Boolean)));
}

function buildTicketFromCandidate(
  candidate: CandidateRow,
  current: PaperOrderTicketState,
  currentPrice: number | null,
  lastScanAt: string | null,
): PaperOrderTicketState {
  const plan = candidate.analysisItem?.recommendation.trade_plans.find((item) => item.mode === "swing")
    ?? candidate.analysisItem?.recommendation.trade_plans[0];
  const entry = plan ? (plan.entry_low + plan.entry_high) / 2 : candidate.entryLow ?? currentPrice ?? current.limitPrice ?? null;
  const stopLoss = plan?.stop_loss ?? candidate.stopLoss ?? null;
  const target = plan?.target_1 ?? candidate.target1 ?? candidate.target2 ?? null;
  const confidence = candidate.confidence ?? undefined;
  const scanText = lastScanAt ? `scan=${new Date(lastScanAt).toLocaleString()}` : "latest scan";

  return {
    ...current,
    symbol: candidate.symbol,
    side: candidate.signal === "REJECT" ? current.side : "BUY",
    type: "LIMIT",
    limitPrice: entry ? roundPrice(entry) : null,
    stopPrice: null,
    stopLoss: stopLoss ? roundPrice(stopLoss) : null,
    target: target ? roundPrice(target) : null,
    sourceSignal: candidate.signal,
    sourceScore: candidate.score,
    sourceConfidence: confidence ?? null,
    notes: appendTicketNote(
      current.notes,
      `Auto-filled from ${scanText}: ${candidate.signal}, score ${candidate.score === null || candidate.score === undefined ? "N/A" : candidate.score.toFixed(1)}, confidence ${confidence === undefined || confidence === null ? "n/a" : Math.round(confidence * 100) + "%"}.`,
    ),
  };
}

function appendTicketNote(existing: string | undefined, note: string) {
  const trimmed = existing?.trim();
  if (!trimmed) {
    return note;
  }
  if (trimmed.includes(note)) {
    return trimmed;
  }
  return `${trimmed} | ${note}`;
}

function roundPrice(value: number) {
  return Math.round(value * 20) / 20;
}

function updateDashboardQuote(
  dashboard: PaperTradingDashboardResponse | null,
  symbol: string,
  currentPrice: number,
): PaperTradingDashboardResponse | null {
  if (!dashboard) {
    return dashboard;
  }

  return {
    ...dashboard,
    positions: dashboard.positions.map((position) => {
      if (position.symbol !== symbol) {
        return position;
      }
      const unrealizedPnl = (currentPrice - position.avg_entry_price) * position.qty;
      const unrealizedPnlPercent = position.avg_entry_price
        ? ((currentPrice - position.avg_entry_price) / position.avg_entry_price) * 100
        : 0;
      return {
        ...position,
        current_price: currentPrice,
        unrealized_pnl: roundMoney(unrealizedPnl),
        unrealized_pnl_percent: roundMoney(unrealizedPnlPercent),
      };
    }),
    selected_workspace:
      dashboard.selected_workspace?.symbol === symbol
        ? {
            ...dashboard.selected_workspace,
            current_price: currentPrice,
          }
        : dashboard.selected_workspace,
  };
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function buildGuidePath(
  candles: { timestamp: string }[],
  value: number,
  xFor: (index: number) => number,
  yFor: (price: number) => number,
) {
  return candles.map((_: { timestamp: string }, index: number) => `${index === 0 ? "M" : "L"} ${xFor(index)} ${yFor(value)}`).join(" ");
}

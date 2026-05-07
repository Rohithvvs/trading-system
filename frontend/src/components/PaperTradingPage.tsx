import { useEffect, useMemo, useState, useRef } from "react";
import { InfoTooltip } from './InfoTooltip';
import { TOOLTIPS } from '../constants/tooltips';

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
  squareOffAllPositions,
  fetchUnreadNotifications,
  markNotificationsRead,
  fetchAnalytics,
  fetchAlerts,
  createAlert,
  deleteAlert,
  // token APIs
  getTokenStatus,
  setRefreshToken,
  manualRefreshToken,
} from "../api";
import TokenStatus from "./TokenStatus";
import type {
  CandidateRow,
  PaperOrder,
  PaperOrderTicketState,
  PaperPosition,
  PaperTradeHistoryItem,
  PaperTradingDashboardResponse,
  RecommendationPrefillRequest,
} from "../types";

type PaperTradingPageProps = {
  recommendationPrefill?: RecommendationPrefillRequest | null;
  onPrefillConsumed?: () => void;
  scannerCandidates?: CandidateRow[];
  lastScanAt?: string | null;
};

type PaperPanelTab = "positions" | "orders" | "history" | "analytics" | "account";

// Chart.js global loaded from CDN
declare const Chart: any;

const DEFAULT_TICKET: PaperOrderTicketState = {
  symbol: "INFY-EQ",
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

export function PaperTradingPage({
  recommendationPrefill,
  onPrefillConsumed,
  scannerCandidates = [],
  lastScanAt = null,
}: PaperTradingPageProps) {
  // Token status is useful in Paper Trading page; not required but handy
  useEffect(() => {
    let mounted = true;
    async function loadToken() {
      try {
        await getTokenStatus();
      } catch {
        // ignore
      }
    }
    void loadToken();
    return () => { mounted = false; };
  }, []);

  // Insert TokenStatus panel in account tab when active
  const initialSymbol = recommendationPrefill?.symbol ?? scannerCandidates[0]?.symbol ?? DEFAULT_TICKET.symbol;
  const [dashboard, setDashboard] = useState<PaperTradingDashboardResponse | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string>(initialSymbol);
  const [ticket, setTicket] = useState<PaperOrderTicketState>({ ...DEFAULT_TICKET, symbol: initialSymbol });
  const [listTab, setListTab] = useState<PaperPanelTab>("positions");
  const [resetBalance, setResetBalance] = useState(100000);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isLivePricing, setIsLivePricing] = useState(true);
  const [accountSummary, setAccountSummary] = useState<any | null>(null);
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);
  const [toasts, setToasts] = useState<Array<{ id: number; message: string; level: string }>>([]);
  const seenNotifications = useRef<Set<number>>(new Set());

  useEffect(() => {
    let mounted = true;
    async function loadSummary() {
      try {
        const data = await fetchPaperAccountSummary();
        if (mounted) setAccountSummary(data);
      } catch (err) {
        console.warn("Failed to load account summary", err);
      }
    }
    void loadSummary();
    const id = window.setInterval(() => void loadSummary(), 10000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, []);

  // Check for offline gap replay summary on mount and show banner if applicable
  useEffect(() => {
    async function checkGapReplay() {
      try {
        const resp = await fetch("/api/paper-trading/gap-replay-summary");
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
        /* ignore */
      }
    }
    void checkGapReplay();
  }, []);

  // Initial dashboard load with retry (handles backend startup/gap-replay)
  useEffect(() => {
    let mounted = true;
    let retryTimeout: ReturnType<typeof setTimeout> | null = null;

    async function loadInitial(retryCount = 0) {
      try {
        setError(null);
        const data = await fetchPaperTradingDashboard(selectedSymbol);
        if (mounted) setDashboard(data);
      } catch (err) {
        // Retry a few times in case backend is still starting
        // eslint-disable-next-line no-console
        console.error("[PaperTrading] Load failed (attempt", retryCount + 1, "):", err);
        if (mounted && retryCount < 3) {
          retryTimeout = setTimeout(() => void loadInitial(retryCount + 1), 2000);
        } else if (mounted) {
          setError("Could not connect to server. Please refresh.");
        }
      }
    }

    void loadInitial();
    return () => {
      mounted = false;
      if (retryTimeout) clearTimeout(retryTimeout);
    };
  }, []);

  // Poll dashboard periodically so UI stays fresh
  useEffect(() => {
    let mounted = true;
    async function refresh() {
      try {
        const data = await fetchPaperTradingDashboard(selectedSymbol);
        if (mounted) setDashboard(data);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("[PaperTrading] Auto-refresh failed:", err);
      }
    }
    const id = window.setInterval(() => void refresh(), 10000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, [selectedSymbol]);

  useEffect(() => {
    if (!isLivePricing) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void loadLiveQuote(selectedSymbol);
    }, 1000);
    return () => window.clearInterval(intervalId);
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
      const response = await fetchPaperTradingDashboard(symbol ?? selectedSymbol);
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
      const response = await fetchPaperTradingDashboard(symbol ?? selectedSymbol);
      setDashboard((current) => {
        if (!current) {
          return response;
        }
        return {
          ...current,
          account: response.account,
          positions: response.positions,
          open_orders: response.open_orders,
          order_history: response.order_history,
          trades: response.trades,
          symbols: response.symbols,
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

  async function loadLiveQuote(symbol: string) {
    if (!dashboard) {
      return;
    }
    try {
      const quote = await fetchPaperQuote(symbol);
      setDashboard((current) => updateDashboardQuote(current, quote.symbol, quote.current_price));
    } catch {
      setIsLivePricing(false);
      setStatusMessage("Live price paused because the quote request failed. Use Refresh to reload the full dashboard.");
    }
  }

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
    setIsBusy(true);
    setError(null);
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
        const response = await placePaperOrder(ticket);
        setStatusMessage(response.message);
        // Refresh positions and account immediately after a successful order
        await loadPositions(ticket.symbol);
        try {
          const acct = await fetchPaperAccountSummary();
          setAccountSummary(acct);
        } catch (e) {
          // non-fatal
          console.warn('Failed to refresh account after placing order', e);
        }
        setSelectedSymbol(ticket.symbol);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to place order.");
    } finally {
      setIsBusy(false);
    }
  }

  function handleQuickOrder(side: "BUY" | "SELL", symbol?: string) {
    const normalized = (symbol ?? selectedSymbol ?? ticket.symbol).trim().toUpperCase();
    if (!normalized) return;
    setTicket((current) => ({ ...current, symbol: normalized, side, type: "MARKET" }));
    setSelectedSymbol(normalized);
    // Scroll the order ticket into view
    try {
      const el = document.querySelector(".paper-right") as HTMLElement | null;
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch {
      /* ignore */
    }
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
      await loadPositions(selectedSymbol);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to cancel order.");
    } finally {
      setIsBusy(false);
    }
  }

  function handleEditOrder(order: PaperOrder) {
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
    // switch to ticket view if needed
    setListTab("orders");
  }

  async function handleDeleteOrder(orderId: number) {
    if (!confirm("Cancel this order?")) return;
    setIsBusy(true);
    try {
      const response = await deletePaperOrder(orderId);
      setStatusMessage(response.message);
      await loadPositions(selectedSymbol);
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
      await loadPositions(selectedSymbol);
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
      const el = document.querySelector(".paper-right") as HTMLElement | null;
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch {
      /* ignore */
    }
  }

  async function handleSquareOffAll() {
    if (!confirm("Square off ALL positions?")) return;
    setIsBusy(true);
    try {
      const resp = await squareOffAllPositions();
      setDashboard(resp);
      setStatusMessage("All positions squared off.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to square off all positions.");
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
            setToasts((t) => [...t, { id: n.id, message: n.message, level: n.level }]);
            window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== n.id)), 6000);
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
          <p className="section-label">Paper Trading</p>
          <h1>Cash-only execution simulator</h1>
          <p className="muted-copy">
            TradingView-style practice flow for Nifty 500 cash stocks, connected to your analysis and trade-plan outputs.
          </p>
        </div>
        <div className="paper-header-actions">
          <label className="inline-field">
            <span>Reset balance</span>
            <input type="number" min={1000} step={1000} value={resetBalance} onChange={(event) => setResetBalance(Number(event.target.value))} />
          </label>
          <button type="button" className="button ghost-button" onClick={() => void loadDashboard(selectedSymbol)} disabled={isBusy}>
            Refresh
          </button>
          <button type="button" className="button ghost-button" onClick={() => setIsLivePricing((current) => !current)}>
            {isLivePricing ? "Live price on" : "Live price off"}
          </button>
          <button type="button" className="button primary-button" onClick={handleReset} disabled={isBusy}>
            Reset account
          </button>
        </div>
      </section>

      <AccountSummaryStrip dashboard={dashboard} />

      <PaperAccountWidgets
        summary={accountSummary}
        onQuickBuy={(symbol?: string) => handleQuickOrder("BUY", symbol)}
        onQuickSell={(symbol?: string) => handleQuickOrder("SELL", symbol)}
      />

      {/* Toast area for notifications */}
      <div style={{ position: 'fixed', right: 20, top: 80, zIndex: 1200 }}>
        {toasts.map((t) => (
          <div key={t.id} style={{ marginBottom: 8, padding: 12, borderRadius: 6, minWidth: 260, boxShadow: '0 2px 6px rgba(0,0,0,0.12)', background: t.level === 'success' ? '#083f07' : t.level === 'error' ? '#4a0b0b' : '#083544', color: '#fff' }}>
            <div style={{ fontWeight: 600 }}>{t.message}</div>
          </div>
        ))}
      </div>

      {statusMessage ? <section className="panel success-banner"><p>{statusMessage}</p></section> : null}
      {error ? <section className="panel error-state"><h2>Paper trading action failed</h2><p>{error}</p></section> : null}

      <section className="paper-layout">
        <section className="paper-left">
          <section className="panel paper-tabs-panel">
            <div className="detail-tabs" role="tablist" aria-label="Paper trading data tabs">
              {[
                ["positions", "Positions"],
                ["orders", "Open Orders"],
                ["history", "History"],
                ["analytics", "Analytics"],
                ["alerts", "Alerts"],
                ["account", "Account"],
              ].map(([id, label]) => (
                <button
                  key={id}
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
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                  <button type="button" className="button ghost-button" onClick={() => void handleSquareOffAll()} disabled={isBusy || !(dashboard?.positions?.length)}>
                    Square Off ALL
                  </button>
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.SQUARE_OFF_ALL} />
                </div>
                {dashboard === null ? (
                  <div className="loading-spinner">Loading positions...</div>
                ) : (dashboard.positions?.length ?? 0) === 0 ? (
                  <div className="empty-state">No open positions</div>
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
                <div className="loading-spinner">Loading open orders...</div>
              ) : (dashboard.open_orders?.length ?? 0) === 0 ? (
                <div className="empty-state">No open orders</div>
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
                <div className="loading-spinner">Loading trade history...</div>
              ) : (dashboard.trades?.length ?? 0) === 0 ? (
                <div className="empty-state">No trade history</div>
              ) : (
                <HistoryTable trades={dashboard.trades} />
              )
            ) : null}

            {listTab === "analytics" ? (
              dashboard === null ? (
                <div className="loading-spinner">Loading analytics...</div>
              ) : (
                <AnalyticsPanel />
              )
            ) : null}
            {listTab === "alerts" ? (
              <AlertsPanel onRefresh={() => void loadPositions(selectedSymbol)} />
            ) : null}
            {listTab === "account" ? (
              <AccountPanel onAccountUpdate={(a) => setAccountSummary(a)} onDashboardUpdate={(d) => setDashboard(d)} />
            ) : null}
          </section>
        </section>

        <section className="paper-right">
          <OrderTicketCard
            symbols={ticketSymbols}
            scannerSymbols={scannerSymbols}
            ticket={ticket}
            onChange={setTicket}
            onSymbolSelect={handleSymbolSelect}
            onPlace={() => void handlePlaceOrder()}
            isBusy={isBusy}
            currentPrice={workspace?.current_price ?? null}
            riskMetrics={riskMetrics}
            maxRiskPercent={dashboard?.account.max_risk_per_trade ?? 0.02}
            availableCash={dashboard?.account.available_cash ?? null}
            scannerCandidate={selectedScannerCandidate}
            lastScanAt={lastScanAt}
          />

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="section-label">Selected symbol</p>
                <h2>{workspace?.symbol ?? selectedSymbol}</h2>
              </div>
              <div className="meta-inline">
                <span className="helper-chip">Current ₹{workspace?.current_price.toFixed(2) ?? "--"}</span>
                {workspace?.source_signal ? <span className={`signal-badge signal-${workspace.source_signal.toLowerCase()}`}>{workspace.source_signal}</span> : null}
              </div>
            </div>
            <PaperChart workspace={workspace} ticket={ticket} />
          </section>

          <TradeDetailsCard
            position={selectedPosition}
            orders={selectedOrders}
            onPositionChange={(position) => void handleSyncPosition(position)}
          />
        </section>
      </section>
    </main>
  );
}

function AccountSummaryStrip({ dashboard }: { dashboard: PaperTradingDashboardResponse | null }) {
  const account = dashboard?.account;
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
    <section className="panel">
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
}) {
  const [trailingStopPercent, setTrailingStopPercent] = useState(2);
  const [allocationPercent, setAllocationPercent] = useState(10);
  const [previewOpen, setPreviewOpen] = useState(false);
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
          <select value={ticket.symbol} onChange={(event) => onSymbolSelect(event.target.value)}>
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
          <select value={ticket.side} onChange={(event) => onChange({ ...ticket, side: event.target.value as "BUY" | "SELL" })}>
            <option value="BUY">Buy</option>
            <option value="SELL">Sell</option>
          </select>
        </label>

        <label className="filter-field">
          <span>
            Order type
            <InfoTooltip content={TOOLTIPS.PAPER_TRADING.ORDER_TYPE} />
          </span>
          <select value={ticket.type} onChange={(event) => onChange({ ...ticket, type: event.target.value as any })}>
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
          <input type="number" min={1} placeholder="1" value={ticket.qty} onChange={(event) => onChange({ ...ticket, qty: Number(event.target.value) })} />
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
            <Metric label="Score" value={scannerCandidate.score.toFixed(1)} />
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
        <div>
          {qtyError ? <div className="error-state" style={{ display: 'inline-block', padding: 8, marginRight: 8 }}>{qtyError}</div> : null}
          <button type="button" className="button primary-button" onClick={() => setPreviewOpen(true)} disabled={isBusy || !!qtyError}>
            {isBusy ? "Working..." : "Place paper order"}
          </button>
        </div>
      </div>
      {previewOpen ? (
        <div className="panel" style={{ position: 'fixed', left: '50%', top: '20%', transform: 'translateX(-50%)', zIndex: 60, width: 520 }}>
          <div className="panel-header">
            <div>
              <p className="section-label">Order preview</p>
              <h2>Confirm order</h2>
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
              Estimated total {ticket.side === 'BUY' ? 'cost' : 'proceeds'}: ₹{ticket.side === 'BUY' ? ((entryReference ?? 0) * ticket.qty + (ticket.side === 'SELL' ? 0 : 0)).toFixed(2) : ((entryReference ?? 0) * ticket.qty - ((entryReference ?? 0) * ticket.qty * 0.001)).toFixed(2)}
            </p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
              <button type="button" className="button ghost-button" onClick={() => setPreviewOpen(false)}>Cancel</button>
              <button type="button" className="button primary-button" onClick={async () => { setPreviewOpen(false); await onPlace(); }}>
                Confirm
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PositionsTable({
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
    <div className="table-scroll">
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
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((position) => (
            <tr key={position.id} className={selectedSymbol === position.symbol ? "is-selected" : ""}>
              <td><button type="button" className="text-button" onClick={() => onSelect(position.symbol)}>{position.symbol}</button></td>
              <td>{position.qty}</td>
              <td className="number-cell">{position.avg_entry_price.toFixed(2)}</td>
              <td className="number-cell">{position.current_price.toFixed(2)}</td>
              <td className={`number-cell ${position.unrealized_pnl >= 0 ? "text-positive" : "text-negative"}`}>{formatCurrency(position.unrealized_pnl)}</td>
              <td className={`number-cell ${position.unrealized_pnl_percent >= 0 ? "text-positive" : "text-negative"}`}>{position.unrealized_pnl_percent.toFixed(2)}%</td>
              <td className="number-cell">{position.stop_loss?.toFixed(2) ?? "--"}</td>
              <td className="number-cell">{position.target?.toFixed(2) ?? "--"}</td>
              <td className="number-cell">{position.risk_reward_ratio?.toFixed(2) ?? "--"}</td>
              <td style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="button ghost-button small-button" onClick={() => onExit(position)}>Exit</button>
                <button type="button" className="button ghost-button small-button" onClick={() => onClose(position.id)}>Square Off</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OrdersTable({
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
    <div className="table-scroll">
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
              <td style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="button ghost-button small-button" onClick={() => onEdit(order)}>Edit</button>
                <button type="button" className="button ghost-button small-button" onClick={() => onDelete(order.id)}>Cancel</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HistoryTable({ trades }: { trades: PaperTradeHistoryItem[] }) {
  if (!trades.length) {
    return <div className="empty-state"><h2>No trade history</h2><p>Closed paper trades will appear here with holding period and P&amp;L.</p></div>;
  }

  return (
    <div className="table-scroll">
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
            <tr key={trade.id}>
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
  );
}

function AnalyticsPanel() {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const dailyRef = useRef<HTMLCanvasElement | null>(null);
  const cumRef = useRef<HTMLCanvasElement | null>(null);
  const pieRef = useRef<HTMLCanvasElement | null>(null);
  const chartsRef = useRef<{ daily?: any; cum?: any; pie?: any }>({});

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    void (async () => {
      try {
        const resp = await fetchAnalytics();
        if (!mounted) return;
        setData(resp);
      } catch (e: any) {
        setErr(e?.message ?? String(e));
      } finally {
        setLoading(false);
      }
    })();
    return () => {
      mounted = false;
      Object.values(chartsRef.current).forEach((c) => c?.destroy?.());
    };
  }, []);

  useEffect(() => {
    if (!data) return;
    // Daily P&L bar
    try {
      const labels = data.daily_pnl.map((p: any) => p.date);
      const values = data.daily_pnl.map((p: any) => p.pnl);
      const colors = values.map((v: number) => (v >= 0 ? "#1b7a1b" : "#a60b0b"));
      const dctx = dailyRef.current?.getContext("2d");
      if (dctx) {
        chartsRef.current.daily = new Chart(dctx, {
          type: "bar",
          data: {
            labels,
            datasets: [{ label: "Daily P&L", data: values, backgroundColor: colors }],
          },
          options: { responsive: true, plugins: { legend: { display: false } } },
        });
      }

      // Cumulative
      const cLabels = data.cumulative_pnl.map((p: any) => p.date);
      const cValues = data.cumulative_pnl.map((p: any) => p.pnl);
      const cctx = cumRef.current?.getContext("2d");
      if (cctx) {
        chartsRef.current.cum = new Chart(cctx, {
          type: "line",
          data: {
            labels: cLabels,
            datasets: [{ label: "Cumulative P&L", data: cValues, borderColor: "#2b6cff", fill: false }],
          },
          options: { responsive: true },
        });
      }

      // Pie
      const pieCtx = pieRef.current?.getContext("2d");
      if (pieCtx) {
        chartsRef.current.pie = new Chart(pieCtx, {
          type: "pie",
          data: {
            labels: ["Wins", "Losses"],
            datasets: [{ data: [data.wins, data.losses], backgroundColor: ["#2ecc71", "#e74c3c"] }],
          },
          options: { responsive: true },
        });
      }
    } catch (e) {
      console.warn("Failed to render analytics charts", e);
    }
    return () => {
      Object.values(chartsRef.current).forEach((c) => c?.destroy?.());
      chartsRef.current = {} as any;
    };
  }, [data]);

  if (loading) {
    return <div className="empty-state"><h2>Loading analytics...</h2></div>;
  }
  if (err) {
    return <div className="empty-state"><h2>Failed to load analytics</h2><p>{err}</p></div>;
  }
  if (!data) {
    return <div className="empty-state"><h2>No analytics yet</h2></div>;
  }

  return (
    <section>
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <div className="metric-card"><span>Total trades</span><strong>{data.total_trades}</strong><p>Closed trades</p></div>
        <div className="metric-card"><span>Win rate</span><strong>{data.win_rate_pct}%</strong><p>Winning trades percent</p></div>
        <div className="metric-card"><span>Profit factor</span><strong>{data.profit_factor ?? '--'}</strong><p>Sum wins / abs(sum losses)</p></div>
        <div className="metric-card"><span>Average profit</span><strong>{data.average_profit ?? '--'}</strong><p>Avg winning trade P&L</p></div>
        <div className="metric-card"><span>Average loss</span><strong>{data.average_loss ?? '--'}</strong><p>Avg losing trade P&L</p></div>
        <div className="metric-card"><span>Best trade</span><strong>{data.best_trade_symbol ?? '--'} {data.best_trade_amount ? `₹${data.best_trade_amount}` : ''}</strong><p>Highest single trade</p></div>
        <div className="metric-card"><span>Worst trade</span><strong>{data.worst_trade_symbol ?? '--'} {data.worst_trade_amount ? `₹${data.worst_trade_amount}` : ''}</strong><p>Lowest single trade</p></div>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 380px', minWidth: 320 }} className="panel"><canvas ref={dailyRef} /></div>
        <div style={{ flex: '1 1 380px', minWidth: 320 }} className="panel"><canvas ref={cumRef} /></div>
        <div style={{ width: 260 }} className="panel"><canvas ref={pieRef} /></div>
      </div>

      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Holding periods</p><h2>Per-symbol stats</h2></div></div>
        <div className="table-scroll">
          <table className="candidate-table">
            <thead>
              <tr><th>Symbol</th><th>Avg hold (min)</th><th>Total trades</th><th>Win rate</th></tr>
            </thead>
            <tbody>
              {data.holding_periods.map((row: any) => (
                <tr key={row.symbol}><td>{row.symbol}</td><td className="number-cell">{row.avg_holding_minutes.toFixed(1)}</td><td>{row.total_trades}</td><td>{row.win_rate_pct}%</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function AlertsPanel({ onRefresh }: { onRefresh?: () => void }) {
  const [loading, setLoading] = useState(false);
  const [symbol, setSymbol] = useState("");
  const [condition, setCondition] = useState<"<=" | ">=">(">=");
  const [price, setPrice] = useState<number | "">("");
  const [alerts, setAlerts] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await fetchAlerts();
      setAlerts(data || []);
    } catch (e: any) {
      setError(String(e?.message ?? e));
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

  if (loading) return <div className="empty-state"><h2>Loading alerts...</h2></div>;

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
      </section>
    </section>
  );
}

function AccountPanel({ onAccountUpdate, onDashboardUpdate }: { onAccountUpdate?: (d: any) => void; onDashboardUpdate?: (d: any) => void }) {
  const [account, setAccount] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState<number>(100000);
  const [page, setPage] = useState<number>(1);
  const [transactions, setTransactions] = useState<any | null>(null);
  const [localMessage, setLocalMessage] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const perPage = 20;

  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoading(true);
      try {
        const acct = await fetchPaperAccountSummary();
        if (!mounted) return;
        setAccount(acct);
        setStarting(acct.starting_balance ?? 100000);
      } catch (e) {
        console.warn("Failed to load account summary", e);
      } finally {
        setLoading(false);
      }
    }
    void load();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
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
      setStatusMessage("Starting capital updated.");
      setTimeout(() => setStatusMessage(null), 3000);
    } catch (e: any) {
      setError(String(e?.message ?? e));
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

  if (loading) {
    return <div className="empty-state"><h2>Loading account...</h2></div>;
  }

  return (
    <section>
      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Account Summary</p><h2>Summary</h2></div></div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <div className="metric-card"><span>Starting Capital</span><strong>₹{(account?.starting_balance ?? starting).toLocaleString()}</strong></div>
          <div className="metric-card"><span>Current Total Capital</span><strong>₹{((account?.starting_balance ?? 0) + (account?.realized_pnl ?? 0)).toFixed(2)}</strong></div>
          <div className="metric-card"><span>Available Funds</span><strong>₹{(account?.available_cash ?? 0).toFixed(2)}</strong></div>
          <div className="metric-card"><span>Margin Used</span><strong>₹{(account?.total_invested ?? 0).toFixed(2)}</strong></div>
          <div className="metric-card"><span>Total Realized P&L</span><strong>₹{(account?.realized_pnl ?? 0).toFixed(2)}</strong></div>
          <div className="metric-card"><span>Total Unrealized P&L</span><strong>₹{(account?.unrealized_pnl ?? 0).toFixed(2)}</strong></div>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Configuration</p><h2>Account Settings</h2></div></div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <label style={{ display: 'flex', flexDirection: 'column' }}>
            Set Starting Capital
            <input type="number" value={starting} onChange={(e) => setStarting(Number(e.target.value || 0))} style={{ width: 200, marginTop: 6 }} />
          </label>
          <div>
            <button className="button" onClick={() => void handleSaveStarting()} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
            <button className="button ghost-button" onClick={() => void handleResetAccount()} style={{ marginLeft: 8 }} disabled={busy}>Reset Account</button>
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

      <section className="panel">
        <div className="panel-header"><div><p className="section-label">FYERS Token</p><h2>Token Management</h2></div></div>
        <TokenStatus />
      </section>
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
        <Metric label="Current" value={position.current_price.toFixed(2)} />
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
      `Auto-filled from ${scanText}: ${candidate.signal}, score ${candidate.score.toFixed(1)}, confidence ${confidence === undefined ? "n/a" : Math.round(confidence * 100) + "%"}.`,
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

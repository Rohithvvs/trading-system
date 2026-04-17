import { useEffect, useMemo, useState } from "react";

import {
  cancelPaperOrder,
  closePaperPosition,
  fetchPaperTradingDashboard,
  fetchPaperQuote,
  placePaperOrder,
  prefillPaperTrade,
  resetPaperTradingAccount,
  updatePaperPosition,
} from "../api";
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

type PaperPanelTab = "positions" | "orders" | "history";

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

  useEffect(() => {
    void loadDashboard();
  }, []);

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
      const response = await placePaperOrder(ticket);
      setStatusMessage(response.message);
      const updated = await fetchPaperTradingDashboard(ticket.symbol);
      setDashboard(updated);
      setSelectedSymbol(ticket.symbol);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to place order.");
    } finally {
      setIsBusy(false);
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
      const updated = await fetchPaperTradingDashboard(selectedSymbol);
      setDashboard(updated);
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
      const updated = await fetchPaperTradingDashboard(selectedSymbol);
      setDashboard(updated);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to close position.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSyncPosition(position: PaperPosition) {
    setIsBusy(true);
    try {
      const response = await updatePaperPosition({
        id: position.id,
        stop_loss: position.stop_loss ?? null,
        target: position.target ?? null,
      });
      setStatusMessage(response.message);
      const updated = await fetchPaperTradingDashboard(selectedSymbol);
      setDashboard(updated);
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
              <PositionsTable
                positions={dashboard?.positions ?? []}
                selectedSymbol={selectedSymbol}
                onSelect={(symbol) => {
                  setSelectedSymbol(symbol);
                  void loadDashboard(symbol);
                }}
                onClose={(positionId) => void handleClosePosition(positionId)}
              />
            ) : null}

            {listTab === "orders" ? (
              <OrdersTable
                orders={dashboard?.open_orders ?? []}
                selectedSymbol={selectedSymbol}
                onSelect={(symbol) => {
                  setSelectedSymbol(symbol);
                  void loadDashboard(symbol);
                }}
                onCancel={(orderId) => void handleCancelOrder(orderId)}
              />
            ) : null}

            {listTab === "history" ? (
              <HistoryTable trades={dashboard?.trades ?? []} />
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

  return (
    <section className="summary-row">
      {metrics.map(([label, value]) => (
        <article key={label} className="metric-card">
          <span>{label}</span>
          <strong>{value}</strong>
          <p>{label === "Available cash" ? "Balance after reserving pending buy orders." : "Paper account metric."}</p>
        </article>
      ))}
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

  function markBracketOrder() {
    onChange({
      ...ticket,
      notes: appendTicketNote(ticket.notes, "Bracket/OCO plan: keep target and stop-loss paired; cancel the other exit when one is filled."),
    });
  }

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
          <span>Symbol</span>
          <select value={ticket.symbol} onChange={(event) => onSymbolSelect(event.target.value)}>
            {symbols.map((symbol) => (
              <option key={symbol} value={symbol}>
                {scannerSet.has(symbol) ? `${symbol} - latest scan` : symbol}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-field">
          <span>Side</span>
          <select value={ticket.side} onChange={(event) => onChange({ ...ticket, side: event.target.value as "BUY" | "SELL" })}>
            <option value="BUY">Buy</option>
            <option value="SELL">Sell</option>
          </select>
        </label>

        <label className="filter-field">
          <span>Order type</span>
          <select value={ticket.type} onChange={(event) => onChange({ ...ticket, type: event.target.value as "MARKET" | "LIMIT" | "STOP" })}>
            <option value="MARKET">Market</option>
            <option value="LIMIT">Limit</option>
            <option value="STOP">Stop</option>
          </select>
        </label>

        <label className="filter-field">
          <span>Quantity</span>
          <input type="number" min={1} value={ticket.qty} onChange={(event) => onChange({ ...ticket, qty: Number(event.target.value) })} />
        </label>

        {ticket.type === "LIMIT" ? (
          <label className="filter-field">
            <span>Limit price</span>
            <input type="number" min={0.01} step="0.05" value={ticket.limitPrice ?? ""} onChange={(event) => onChange({ ...ticket, limitPrice: Number(event.target.value) || null })} />
          </label>
        ) : null}

        {ticket.type === "STOP" ? (
          <label className="filter-field">
            <span>Stop trigger</span>
            <input type="number" min={0.01} step="0.05" value={ticket.stopPrice ?? ""} onChange={(event) => onChange({ ...ticket, stopPrice: Number(event.target.value) || null })} />
          </label>
        ) : null}

        <label className="filter-field">
          <span>Stop-loss</span>
          <input type="number" min={0.01} step="0.05" value={ticket.stopLoss ?? ""} onChange={(event) => onChange({ ...ticket, stopLoss: Number(event.target.value) || null })} />
        </label>

        <label className="filter-field">
          <span>Target</span>
          <input type="number" min={0.01} step="0.05" value={ticket.target ?? ""} onChange={(event) => onChange({ ...ticket, target: Number(event.target.value) || null })} />
        </label>
      </div>

      <label className="filter-field">
        <span>Notes</span>
        <input value={ticket.notes ?? ""} onChange={(event) => onChange({ ...ticket, notes: event.target.value })} />
      </label>

      <div className="broker-helper-grid">
        <label className="filter-field">
          <span>Trailing stop %</span>
          <input type="number" min={0.1} step="0.1" value={trailingStopPercent} onChange={(event) => setTrailingStopPercent(Number(event.target.value) || 0)} />
        </label>
        <label className="filter-field">
          <span>Cash allocation %</span>
          <input type="number" min={1} max={100} step="1" value={allocationPercent} onChange={(event) => setAllocationPercent(Number(event.target.value) || 0)} />
        </label>
        <button type="button" className="button ghost-button" onClick={applyTrailingStop}>
          Apply trailing SL
        </button>
        <button type="button" className="button ghost-button" onClick={applySuggestedQuantity}>
          Use suggested qty {suggestedQty}
        </button>
        <button type="button" className="button ghost-button" onClick={markBracketOrder}>
          Mark bracket / OCO
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
        <button type="button" className="button primary-button" onClick={onPlace} disabled={isBusy}>
          {isBusy ? "Working..." : "Place paper order"}
        </button>
      </div>
    </section>
  );
}

function PositionsTable({
  positions,
  selectedSymbol,
  onSelect,
  onClose,
}: {
  positions: PaperPosition[];
  selectedSymbol: string;
  onSelect: (symbol: string) => void;
  onClose: (positionId: number) => void;
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
            <th>Avg entry</th>
            <th>Current</th>
            <th>Unrealized</th>
            <th>Stop</th>
            <th>Target</th>
            <th>R:R</th>
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
              <td className="number-cell">{position.stop_loss?.toFixed(2) ?? "--"}</td>
              <td className="number-cell">{position.target?.toFixed(2) ?? "--"}</td>
              <td className="number-cell">{position.risk_reward_ratio?.toFixed(2) ?? "--"}</td>
              <td><button type="button" className="button ghost-button small-button" onClick={() => onClose(position.id)}>Close</button></td>
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
  onCancel,
}: {
  orders: PaperOrder[];
  selectedSymbol: string;
  onSelect: (symbol: string) => void;
  onCancel: (orderId: number) => void;
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
              <td><button type="button" className="button ghost-button small-button" onClick={() => onCancel(order.id)}>Cancel</button></td>
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
              <td>{trade.holding_period_hours.toFixed(1)}h</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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

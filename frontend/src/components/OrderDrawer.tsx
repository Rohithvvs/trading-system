import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { InfoTooltip } from "./InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";
import {
  fetchPaperAccountSummary,
  fetchPaperQuote,
  fetchPendingPaperOrders,
  fetchPositions,
  fetchPaperTrades,
  placePaperOrder,
  updatePaperOrder,
  prefillPaperTrade,
  invalidatePaperCaches,
} from "../api";

import type { PaperOrderTicketState, CandidateRow, RecommendationPrefillRequest } from "../types";
import { usePaperOrder } from "../contexts/PaperOrderContext";
import { useToast } from "../design-system";
import {
  extractPaperAvailableCash,
  extractPaperMaxRiskPerTrade,
  logPaperCapital,
} from "../utils/paperCapital";

const DEFAULT_TICKET: PaperOrderTicketState = {
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

/** Normalize UI/broker symbols to the canonical cash form used by the API. */
function toCanonicalSymbol(raw: string | undefined | null): string {
  if (!raw) return "INFY";
  let s = raw.trim().toUpperCase();
  if (s.startsWith("NSE:")) s = s.slice(4);
  else if (s.startsWith("BSE:")) s = s.slice(4);
  else if (s.includes(":")) s = s.split(":")[1] ?? s;
  if (s.endsWith("-EQ")) s = s.slice(0, -3);
  return s || "INFY";
}

type OrderDrawerProps = {
  symbols?: string[];
  scannerSymbols?: string[];
  scannerCandidate?: CandidateRow | null;
  lastScanAt?: string | null;
  onOrderSuccess?: () => void;
  onOrderPlaced?: () => void;
};

export function OrderDrawer({
  symbols = [],
  scannerSymbols = [],
  scannerCandidate = null,
  lastScanAt = null,
  onOrderSuccess,
  onOrderPlaced,
}: OrderDrawerProps) {
  const { drawerState, closeOrderDrawer, ticketRef } = usePaperOrder();
  const toast = useToast();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState<PaperOrderTicketState>(DEFAULT_TICKET);
  const [isBusy, setIsBusy] = useState(false);
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string>(() => crypto.randomUUID());
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [lastSuccessfulPrice, setLastSuccessfulPrice] = useState<number | null>(null);
  const [lastPriceAt, setLastPriceAt] = useState<number | null>(null);
  const [availableCash, setAvailableCash] = useState<number | null>(null);
  const [accountLoaded, setAccountLoaded] = useState(false);
  const [maxRiskPercent, setMaxRiskPercent] = useState(0.02);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [localSymbols, setLocalSymbols] = useState<string[]>(symbols);
  const [quoteStatus, setQuoteStatus] = useState<"idle" | "loading" | "live" | "degraded" | "error">("idle");
  const drawerRef = useRef<HTMLDivElement>(null);

  const isMobile = typeof window !== "undefined" && window.matchMedia("(max-width: 768px)").matches;
  const isTablet = typeof window !== "undefined" && window.matchMedia("(max-width: 1024px)").matches;

  // Hooks must run unconditionally — never after an early return (blank-page crash).
  const scannerSet = useMemo(() => new Set(scannerSymbols), [scannerSymbols]);
  const allSymbols = useMemo(() => {
    const set = new Set(
      [...localSymbols, ...symbols, ticket.symbol, drawerState.symbol]
        .filter(Boolean)
        .map((s) => toCanonicalSymbol(s)),
    );
    return Array.from(set);
  }, [localSymbols, symbols, ticket.symbol, drawerState.symbol]);

  useEffect(() => {
    if (symbols.length > 0) {
      setLocalSymbols(symbols.map(toCanonicalSymbol));
    }
  }, [symbols]);

  // Open/edit when drawer state changes (open flag + payload identity)
  useEffect(() => {
    if (!drawerState.open) {
      setStatusMessage(null);
      setError(null);
      setQuoteStatus("idle");
      setAccountLoaded(false);
      setAvailableCash(null);
      return;
    }

    setError(null);
    setStatusMessage(null);
    setAccountLoaded(false);
    setAvailableCash(null);

    if (drawerState.orderId) {
      setEditingOrderId(drawerState.orderId);
      void loadOrderForEdit(drawerState.orderId);
    } else {
      setEditingOrderId(null);
      void loadInitialData(drawerState.symbol, drawerState.side, drawerState.prefill);
    }
    // Focus drawer for a11y + ESC
    requestAnimationFrame(() => drawerRef.current?.focus());
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loaders are stable enough; state identity drives re-open
  }, [
    drawerState.open,
    drawerState.symbol,
    drawerState.side,
    drawerState.orderId,
    drawerState.prefill,
  ]);

  async function loadOrderForEdit(orderId: number) {
    setIsBusy(true);
    setQuoteStatus("loading");
    try {
      const { fetchPendingPaperOrders } = await import("../api");
      const orders = await fetchPendingPaperOrders();
      const order = orders.find((o: any) => o.id === orderId);
      if (order) {
        const nextTicket: PaperOrderTicketState = {
          symbol: toCanonicalSymbol(order.symbol),
          side: order.side,
          type: order.type,
          productType: order.product_type,
          qty: order.qty,
          limitPrice: order.price ?? null,
          stopPrice: order.stop_price ?? null,
          stopLoss: order.stop_loss ?? null,
          target: order.target ?? null,
          notes: order.notes ?? "",
          sourceSignal: order.source_signal ?? null,
          sourceScore: order.source_score ?? null,
          sourceConfidence: order.source_confidence ?? null,
        };
        setTicket(nextTicket);
        ticketRef.current = nextTicket;
      }
      const sym = toCanonicalSymbol(order?.symbol ?? "INFY");
      const [quote, acct] = await Promise.all([
        fetchPaperQuote(sym).catch(() => null),
        fetchPaperAccountSummary({ force: true }).catch(() => null),
      ]);
      applyQuote(quote);
      if (acct) {
        const cash = extractPaperAvailableCash(acct);
        setAvailableCash(cash);
        setMaxRiskPercent(extractPaperMaxRiskPerTrade(acct));
        setAccountLoaded(true);
        logPaperCapital("order-drawer", "account_loaded_edit", acct, {
          resolved_available_cash: cash,
        });
      } else {
        setAccountLoaded(true);
      }
    } catch (e) {
      console.warn("Failed to load order for edit", e);
      setQuoteStatus("error");
      setError(e instanceof Error ? e.message : "Failed to load order.");
      setAccountLoaded(true);
    } finally {
      setIsBusy(false);
    }
  }

  function buildTicketFromPrefill(
    prefill: RecommendationPrefillRequest,
    side?: "BUY" | "SELL",
  ): PaperOrderTicketState {
    return {
      symbol: toCanonicalSymbol(prefill.symbol),
      side: side ?? "BUY",
      type: "LIMIT",
      qty: 1,
      limitPrice: prefill.suggested_entry ?? null,
      stopPrice: null,
      stopLoss: prefill.suggested_stop ?? null,
      target: prefill.suggested_targets?.[0] ?? null,
      notes: "",
      sourceSignal: String(prefill.recommendation_meta?.signal ?? "BUY"),
      sourceScore: Number(prefill.recommendation_meta?.score ?? 0),
      sourceConfidence: Number(prefill.recommendation_meta?.confidence ?? 0),
    };
  }

  function applyQuote(quote: { current_price?: number; reason?: string | null; is_stale?: boolean } | null) {
    if (quote?.current_price != null && Number(quote.current_price) > 0) {
      const price = Number(quote.current_price);
      setCurrentPrice(price);
      setLastSuccessfulPrice(price);
      setLastPriceAt(Date.now());
      if (quote.is_stale) {
        setQuoteStatus("degraded");
      } else {
        setQuoteStatus("live");
      }
      return;
    }
    setQuoteStatus(quote ? "degraded" : "error");
  }

  async function loadInitialData(
    symbol?: string,
    side?: "BUY" | "SELL",
    prefill?: RecommendationPrefillRequest | null,
  ) {
    setIsBusy(true);
    setQuoteStatus("loading");
    try {
      if (prefill) {
        try {
          const result = await prefillPaperTrade(prefill);
          const ticketFromPrefill: PaperOrderTicketState = {
            symbol: toCanonicalSymbol(result.symbol),
            side: result.side,
            type: result.type,
            qty: result.qty,
            limitPrice: result.limit_price ?? null,
            stopPrice: null,
            stopLoss: result.stop_loss ?? null,
            target: result.target ?? null,
            notes: result.note,
            sourceSignal: String(prefill.recommendation_meta?.signal ?? "BUY"),
            sourceScore: Number(prefill.recommendation_meta?.score ?? 0),
            sourceConfidence: Number(prefill.recommendation_meta?.confidence ?? 0),
          };
          setTicket(ticketFromPrefill);
          ticketRef.current = ticketFromPrefill;
          if (ticketFromPrefill.symbol && !localSymbols.includes(ticketFromPrefill.symbol)) {
            setLocalSymbols((prev) => [...prev, ticketFromPrefill.symbol]);
          }
          const quote = await fetchPaperQuote(ticketFromPrefill.symbol).catch(() => null);
          applyQuote(quote);
          // Prefer prefill entry when quote is missing
          if (!quote?.current_price && prefill.suggested_entry) {
            setCurrentPrice(prefill.suggested_entry);
            setLastSuccessfulPrice(prefill.suggested_entry);
            setLastPriceAt(Date.now());
            setQuoteStatus("degraded");
          }
        } catch (e) {
          console.warn("Failed to prefill order", e);
          // Fall back to raw prefill fields so the drawer still opens with data
          const fallback = buildTicketFromPrefill(prefill, side);
          setTicket(fallback);
          ticketRef.current = fallback;
          if (prefill.suggested_entry) {
            setCurrentPrice(prefill.suggested_entry);
            setLastSuccessfulPrice(prefill.suggested_entry);
            setLastPriceAt(Date.now());
            setQuoteStatus("degraded");
          } else {
            setQuoteStatus("error");
          }
          setError(e instanceof Error ? e.message : "Prefill partially failed — edit fields manually.");
        }
        const acct = await fetchPaperAccountSummary({ force: true }).catch(() => null);
        if (acct) {
          const cash = extractPaperAvailableCash(acct);
          setAvailableCash(cash);
          setMaxRiskPercent(extractPaperMaxRiskPerTrade(acct));
          setAccountLoaded(true);
          logPaperCapital("order-drawer", "account_loaded_prefill", acct, {
            resolved_available_cash: cash,
          });
        } else {
          setAccountLoaded(true);
        }
        return;
      }

      const sym = toCanonicalSymbol(symbol ?? "INFY");
      setTicket((prev) => ({
        ...prev,
        symbol: sym,
        side: side ?? prev.side,
      }));

      const [quote, acct] = await Promise.all([
        fetchPaperQuote(sym).catch(() => null),
        fetchPaperAccountSummary({ force: true }).catch(() => null),
      ]);

      applyQuote(quote);
      if (acct) {
        const cash = extractPaperAvailableCash(acct);
        setAvailableCash(cash);
        setMaxRiskPercent(extractPaperMaxRiskPerTrade(acct));
        setAccountLoaded(true);
        logPaperCapital("order-drawer", "account_loaded", acct, {
          resolved_available_cash: cash,
          symbol: sym,
        });
      } else {
        setAccountLoaded(true);
      }
    } finally {
      setIsBusy(false);
    }
  }

  const displayPrice = currentPrice ?? lastSuccessfulPrice;
  const entryReference =
    ticket.type === "LIMIT"
      ? ticket.limitPrice
      : ticket.type === "STOP"
        ? ticket.stopPrice
        : displayPrice;

  const riskMetrics = useMemo(() => {
    const estimatedCost = entryReference ? entryReference * ticket.qty : 0;
    const riskPerShare = entryReference && ticket.stopLoss ? Math.abs(entryReference - ticket.stopLoss) : 0;
    const rewardPerShare = entryReference && ticket.target ? Math.abs(ticket.target - entryReference) : 0;
    const riskAmount = riskPerShare * ticket.qty;
    const riskReward = riskPerShare > 0 ? rewardPerShare / riskPerShare : 0;
    const riskPercent = availableCash && riskAmount ? (riskAmount / availableCash) * 100 : 0;

    return {
      estimatedCost,
      riskPerShare,
      rewardPerShare,
      riskAmount,
      riskReward,
      riskPercent,
      warning:
        riskPercent > maxRiskPercent * 100
          ? `Risk exceeds account guideline of ${(maxRiskPercent * 100).toFixed(1)}% per trade.`
          : null,
    };
  }, [ticket, entryReference, availableCash, maxRiskPercent]);

  async function handlePlaceOrder() {
    if (!accountLoaded || (ticket.side === "BUY" && availableCash == null)) {
      setError("Paper account capital is still loading. Wait a moment and try again.");
      toast.error("Loading paper account", "Available cash is still loading. Please wait.");
      return;
    }
    if (ticket.side === "BUY" && availableCash != null && riskMetrics.estimatedCost > availableCash + 0.01) {
      const msg = `Estimated cost exceeds available cash (${availableCash.toFixed(2)}).`;
      setError(msg);
      toast.error("Insufficient cash", msg);
      logPaperCapital("order-drawer", "validation_cash_fail", null, {
        availableCash,
        estimatedCost: riskMetrics.estimatedCost,
      });
      return;
    }

    setIsBusy(true);
    setError(null);
    setStatusMessage(null);
    try {
      const normalizedTicket: PaperOrderTicketState = {
        ...ticket,
        symbol: toCanonicalSymbol(ticket.symbol),
      };

      if (editingOrderId) {
        const payload = {
          qty: normalizedTicket.qty,
          limit_price: normalizedTicket.limitPrice,
          stop_price: normalizedTicket.stopPrice,
          stop_loss: normalizedTicket.stopLoss,
          target: normalizedTicket.target,
          type: normalizedTicket.type,
          product_type: normalizedTicket.productType,
        };
        await updatePaperOrder(editingOrderId, payload as any);
        toast.success("✓ Paper Order Updated Successfully");
        invalidatePaperCaches();
        await Promise.all([
          fetchPendingPaperOrders().catch(() => null),
          fetchPositions().catch(() => null),
          fetchPaperAccountSummary().catch(() => null),
        ]);
        setEditingOrderId(null);
        closeOrderDrawer();
        navigate("/paper");
        window.dispatchEvent(new CustomEvent("paper:order-success"));
        onOrderPlaced?.();
        onOrderSuccess?.();
        return;
      }

      await placePaperOrder(normalizedTicket, idempotencyKey);
      setIdempotencyKey(crypto.randomUUID());

      toast.success("✓ Paper Order Placed Successfully");

      invalidatePaperCaches();
      await Promise.all([
        fetchPendingPaperOrders().catch(() => null),
        fetchPositions().catch(() => null),
        fetchPaperAccountSummary().catch(() => null),
        fetchPaperTrades().catch(() => null),
      ]);

      closeOrderDrawer();
      // Paper Desk → Positions tab
      navigate("/paper");
      window.dispatchEvent(new CustomEvent("paper:order-success"));
      onOrderSuccess?.();
      onOrderPlaced?.();
    } catch (requestError) {
      const msg = requestError instanceof Error ? requestError.message : "Failed to place order.";
      setError(msg);
      toast.error("Order failed", msg);
    } finally {
      setIsBusy(false);
    }
  }

  function handleCancel() {
    closeOrderDrawer();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      handleCancel();
    }
  }

  // Conditional render AFTER all hooks — required for React Rules of Hooks
  if (!drawerState.open) {
    return null;
  }

  const priceAgeSec =
    lastPriceAt != null ? Math.max(0, Math.round((Date.now() - lastPriceAt) / 1000)) : null;

  return (
    <>
      <div className="order-drawer-backdrop" onClick={handleCancel} data-testid="order-drawer-backdrop" />
      <div
        ref={drawerRef}
        className={`order-drawer ${isMobile ? "order-drawer--fullscreen" : isTablet ? "order-drawer--tablet" : "order-drawer--desktop"}`}
        role="dialog"
        aria-modal="true"
        aria-label="Place paper order"
        data-testid="order-drawer"
        onKeyDown={handleKeyDown}
        tabIndex={-1}
      >
        <div className="order-drawer-header">
          <div>
            <p className="section-label">Order ticket</p>
            <h2>{editingOrderId ? "Edit paper order" : "Place paper order"}</h2>
          </div>
          <button
            type="button"
            className="order-drawer-close"
            onClick={handleCancel}
            aria-label="Close order panel"
            data-testid="order-drawer-close"
          >
            ×
          </button>
        </div>

        <div className="order-drawer-body">
          <div className="paper-ticket-grid">
            <label className="filter-field">
              <span>
                Symbol
                <InfoTooltip content="Select the stock to trade" />
              </span>
              <select
                data-testid="drawer-symbol-select"
                value={ticket.symbol}
                onChange={(e) => {
                  const sym = toCanonicalSymbol(e.target.value);
                  setTicket({ ...ticket, symbol: sym });
                  void fetchPaperQuote(sym)
                    .then(applyQuote)
                    .catch(() => setQuoteStatus("error"));
                }}
              >
                {allSymbols.map((s) => (
                  <option key={s} value={s}>
                    {scannerSet.has(s) ? `${s} · latest scan` : s}
                  </option>
                ))}
              </select>
            </label>

            <label className="filter-field">
              <span>
                Side
                <InfoTooltip content="BUY opens a position, SELL closes an existing position" />
              </span>
              <select
                data-testid="drawer-side-select"
                value={ticket.side}
                onChange={(e) => setTicket({ ...ticket, side: e.target.value as "BUY" | "SELL" })}
              >
                <option value="BUY">Buy</option>
                <option value="SELL">Sell</option>
              </select>
            </label>

            <label className="filter-field">
              <span>
                Order type
                <InfoTooltip content={TOOLTIPS.PAPER_TRADING.ORDER_TYPE} />
              </span>
              <select
                data-testid="drawer-order-type-select"
                value={ticket.type}
                onChange={(e) => setTicket({ ...ticket, type: e.target.value as any })}
              >
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
              <select
                value={ticket.productType ?? "CNC"}
                onChange={(e) => setTicket({ ...ticket, productType: e.target.value as any })}
              >
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
              <input
                data-testid="drawer-qty-input"
                type="number"
                min={1}
                placeholder="1"
                value={ticket.qty}
                onChange={(e) => setTicket({ ...ticket, qty: Number(e.target.value) })}
              />
            </label>

            {ticket.type !== "MARKET" ? (
              <label className="filter-field">
                <span>
                  {ticket.type === "STOP" || ticket.type === "STOP_LIMIT" ? "Stop trigger" : "Limit price"}
                  <InfoTooltip
                    content={
                      ticket.type === "STOP" || ticket.type === "STOP_LIMIT"
                        ? TOOLTIPS.PAPER_TRADING.STOP_LOSS_FIELD
                        : TOOLTIPS.PAPER_TRADING.LIMIT_PRICE
                    }
                  />
                </span>
                <input
                  type="number"
                  min={0.01}
                  step="0.05"
                  placeholder={ticket.type === "LIMIT" ? "Current price" : ""}
                  value={
                    ticket.type === "LIMIT" || ticket.type === "GTT" || ticket.type === "STOP_LIMIT"
                      ? ticket.limitPrice ?? ""
                      : ticket.stopPrice ?? ""
                  }
                  onChange={(e) =>
                    setTicket({
                      ...ticket,
                      ...(ticket.type === "LIMIT" || ticket.type === "GTT" || ticket.type === "STOP_LIMIT"
                        ? { limitPrice: Number(e.target.value) || null }
                        : { stopPrice: Number(e.target.value) || null }),
                    })
                  }
                />
              </label>
            ) : null}

            <label className="filter-field">
              <span>
                Stop-loss
                <InfoTooltip content={TOOLTIPS.PAPER_TRADING.STOP_LOSS_FIELD} />
              </span>
              <input
                type="number"
                min={0.01}
                step="0.05"
                placeholder="Auto-calculated"
                value={ticket.stopLoss ?? ""}
                onChange={(e) => setTicket({ ...ticket, stopLoss: Number(e.target.value) || null })}
              />
            </label>

            <label className="filter-field">
              <span>
                Target
                <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TARGET_FIELD} />
              </span>
              <input
                type="number"
                min={0.01}
                step="0.05"
                placeholder="Auto-calculated"
                value={ticket.target ?? ""}
                onChange={(e) => setTicket({ ...ticket, target: Number(e.target.value) || null })}
              />
            </label>
          </div>

          <label className="filter-field" style={{ marginTop: 12 }}>
            <span>Notes</span>
            <input
              value={ticket.notes ?? ""}
              onChange={(e) => setTicket({ ...ticket, notes: e.target.value })}
            />
          </label>

          <div className="broker-helper-grid" style={{ marginTop: 12 }}>
            <label className="filter-field" style={{ gridColumn: "1 / -1" }}>
              <span>
                Trailing stop %
                <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TRAILING_STOP} />
              </span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="number"
                  min={0.1}
                  step="0.1"
                  placeholder="2"
                  id="drawer-trailing-stop"
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="button ghost-button"
                  onClick={() => {
                    const pct = Number(
                      (document.getElementById("drawer-trailing-stop") as HTMLInputElement)?.value || 2,
                    );
                    if (entryReference && pct > 0) {
                      const direction = ticket.side === "BUY" ? -1 : 1;
                      setTicket({
                        ...ticket,
                        stopLoss: Math.round(entryReference * (1 + (direction * pct) / 100) * 20) / 20,
                      });
                    }
                  }}
                >
                  Apply
                </button>
              </div>
            </label>
            <label className="filter-field" style={{ gridColumn: "1 / -1" }}>
              <span>
                Cash allocation %
                <InfoTooltip content={TOOLTIPS.PAPER_TRADING.CASH_ALLOCATION} />
              </span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="number"
                  min={1}
                  max={100}
                  step="1"
                  placeholder="10"
                  id="drawer-allocation"
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="button ghost-button"
                  onClick={() => {
                    const pct = Number(
                      (document.getElementById("drawer-allocation") as HTMLInputElement)?.value || 10,
                    );
                    if (availableCash && entryReference && pct > 0) {
                      const qty = Math.max(1, Math.floor((availableCash * (pct / 100)) / entryReference));
                      setTicket({ ...ticket, qty });
                    }
                  }}
                >
                  Apply
                </button>
              </div>
            </label>
          </div>

          {scannerCandidate ? (
            <div className="scan-prefill-box" style={{ marginTop: 12 }}>
              <div>
                <strong>{scannerCandidate.signal} from latest scanner</strong>
                <p>{scannerCandidate.recommendationSummary}</p>
              </div>
              <div className="scan-prefill-metrics">
                <Metric
                  label="Score"
                  value={
                    scannerCandidate.score === null || scannerCandidate.score === undefined
                      ? "N/A"
                      : scannerCandidate.score.toFixed(1)
                  }
                />
                <Metric
                  label="Confidence"
                  value={
                    scannerCandidate.confidence === null
                      ? "--"
                      : `${Math.round(scannerCandidate.confidence * 100)}%`
                  }
                />
                <Metric label="RR" value={scannerCandidate.riskReward?.toFixed(2) ?? "--"} />
                <Metric
                  label="Scan time"
                  value={lastScanAt ? new Date(lastScanAt).toLocaleTimeString() : "--"}
                />
              </div>
            </div>
          ) : null}

          <div className="score-breakdown" style={{ marginTop: 12 }}>
            <Metric
              label={quoteStatus === "degraded" || quoteStatus === "error" ? "Last price" : "Current"}
              value={
                displayPrice
                  ? `₹${displayPrice.toFixed(2)}${
                      priceAgeSec != null && (quoteStatus === "degraded" || quoteStatus === "error")
                        ? ` · ${priceAgeSec}s ago`
                        : ""
                    }`
                  : quoteStatus === "loading"
                    ? "Loading…"
                    : "--"
              }
            />
            <Metric label="Estimated cost" value={formatCurrency(riskMetrics.estimatedCost)} />
            <Metric label="Risk amount" value={formatCurrency(riskMetrics.riskAmount)} />
            <Metric
              label="Risk / Reward"
              value={riskMetrics.riskReward ? riskMetrics.riskReward.toFixed(2) : "--"}
            />
          </div>

          <p className="helper-text" style={{ marginTop: 8 }}>
            Account rule: avoid risking more than {(maxRiskPercent * 100).toFixed(1)}% per trade and
            prefer setups with at least 1:2 risk-reward.
          </p>
          {riskMetrics.warning ? (
            <div className="warning-box" style={{ marginTop: 8 }}>
              <strong>Risk warning</strong>
              <p>{riskMetrics.warning}</p>
            </div>
          ) : null}

          {statusMessage ? (
            <div className="local-toast local-toast--success" style={{ marginTop: 8 }}>
              <span>{statusMessage}</span>
            </div>
          ) : null}
          {error ? (
            <div className="local-toast local-toast--error" style={{ marginTop: 8 }}>
              <span>{error}</span>
            </div>
          ) : null}
        </div>

        <div className="order-drawer-footer">
          <div className="helper-chip">Risk {riskMetrics.riskPercent.toFixed(2)}% of account</div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="button ghost-button"
              onClick={handleCancel}
              disabled={isBusy}
              data-testid="drawer-cancel-button"
            >
              Cancel
            </button>
            <button
              type="button"
              className="button primary-button"
              onClick={() => void handlePlaceOrder()}
              disabled={isBusy}
              data-testid="drawer-place-order-button"
            >
              {isBusy ? "Working..." : "Place Paper Order"}
            </button>
          </div>
        </div>
      </div>
    </>
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

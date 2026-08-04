import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  fetchPaperAccountSummary,
  fetchPaperQuote,
  fetchPendingPaperOrders,
  placePaperOrder,
  prefillPaperTrade,
  updatePaperOrder,
  invalidatePaperCaches,
} from "../api";

import { toCanonicalSymbol } from "../utils/paperOrderNavigation";
import {
  extractPaperAvailableCash,
  extractPaperMaxRiskPerTrade,
  logPaperCapital,
} from "../utils/paperCapital";
import type { PaperOrderNavState } from "../types/paperOrderNav";
import { isPaperOrderNavState } from "../types/paperOrderNav";
import type { PaperOrderTicketState, RecommendationPrefillRequest } from "../types";
import { useToast, Button, Modal } from "../design-system";
import { InfoTooltip } from "../components/InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";

const DEFAULT_TICKET: PaperOrderTicketState = {
  symbol: "INFY",
  side: "BUY",
  type: "LIMIT",
  productType: "CNC",
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

/** Hard ceiling so the page never stays on "Loading…" forever. */
const BOOTSTRAP_TIMEOUT_MS = 12_000;
const QUOTE_POLL_MS = 3_000;

function formatInr(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatNum(value?: number | null, digits = 2): string {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function logPaperOrder(event: string, payload?: Record<string, unknown>) {
  // Structured logs for navigation / load diagnostics (dev + prod console).
  console.info(`[paper-order] ${event}`, payload ?? {});
}

function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new Error(`${label} timed out after ${ms}ms`));
    }, ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        window.clearTimeout(timer);
        reject(err);
      },
    );
  });
}

/**
 * Dedicated full-page Paper Order ticket.
 * Route: /paper-order
 * Does NOT execute until the user confirms in the modal.
 */
export function PaperOrderPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const toast = useToast();

  const navState: PaperOrderNavState = isPaperOrderNavState(location.state)
    ? (location.state as PaperOrderNavState)
    : {};

  const hasNavState = Boolean(
    navState.symbol ||
      navState.prefill ||
      navState.currentPrice != null ||
      navState.orderId != null ||
      navState.signal,
  );

  const initialSymbol = toCanonicalSymbol(
    navState.symbol || searchParams.get("symbol") || navState.prefill?.symbol || "",
  );
  const initialSide =
    (navState.side as "BUY" | "SELL" | undefined) ||
    (searchParams.get("side") === "SELL" ? "SELL" : "BUY");
  const orderIdFromUrl = Number(searchParams.get("orderId") || navState.orderId || 0) || null;
  const returnTo = navState.returnTo || "/scanner";

  const [ticket, setTicket] = useState<PaperOrderTicketState>({
    ...DEFAULT_TICKET,
    symbol: initialSymbol || DEFAULT_TICKET.symbol,
    side: initialSide,
    limitPrice: navState.prefill?.suggested_entry ?? navState.currentPrice ?? null,
    stopLoss: navState.prefill?.suggested_stop ?? null,
    target: navState.prefill?.suggested_targets?.[0] ?? null,
    sourceSignal:
      (navState.signal as string) ??
      String(navState.prefill?.recommendation_meta?.signal ?? "BUY"),
    sourceScore: navState.score ?? (Number(navState.prefill?.recommendation_meta?.score ?? 0) || null),
    sourceConfidence:
      navState.confidence ??
      (Number(navState.prefill?.recommendation_meta?.confidence ?? 0) || null),
  });

  const [currentPrice, setCurrentPrice] = useState<number | null>(navState.currentPrice ?? null);
  const [availableCash, setAvailableCash] = useState<number | null>(null);
  /** False until paper account capital has been applied (or hard-failed). */
  const [accountLoaded, setAccountLoaded] = useState(false);
  const [maxRiskPercent, setMaxRiskPercent] = useState(0.02);
  const [quoteStatus, setQuoteStatus] = useState<"loading" | "live" | "degraded" | "error">("loading");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [pageError, setPageError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editingOrderId, setEditingOrderId] = useState<number | null>(orderIdFromUrl);
  const [meta, setMeta] = useState({
    signal: navState.signal ?? ticket.sourceSignal,
    score: navState.score ?? ticket.sourceScore,
    confidence: navState.confidence ?? ticket.sourceConfidence,
    riskReward: navState.riskReward ?? null,
  });
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());
  const [trailingStopPct, setTrailingStopPct] = useState<string>("2");
  const [cashAllocPct, setCashAllocPct] = useState<string>("10");
  /** Bumps on remount / retry so stale async work is ignored (Strict Mode safe). */
  const loadGenRef = useRef(0);
  const pollAbortRef = useRef<AbortController | null>(null);

  const entryReference = useMemo(() => {
    if (ticket.type === "LIMIT" || ticket.type === "GTT" || ticket.type === "STOP_LIMIT") {
      return ticket.limitPrice ?? currentPrice;
    }
    if (ticket.type === "STOP") return ticket.stopPrice ?? currentPrice;
    return currentPrice;
  }, [ticket, currentPrice]);

  const risk = useMemo(() => {
    const qty = Math.max(0, Number(ticket.qty) || 0);
    const entry = entryReference && entryReference > 0 ? entryReference : 0;
    const estimatedCost = entry * qty;
    const riskPerShare =
      entry && ticket.stopLoss != null ? Math.abs(entry - ticket.stopLoss) : 0;
    const rewardPerShare =
      entry && ticket.target != null ? Math.abs(ticket.target - entry) : 0;
    const riskAmount = riskPerShare * qty;
    const potentialProfit = rewardPerShare * qty;
    const potentialLoss = riskAmount;
    const riskReward = riskPerShare > 0 ? rewardPerShare / riskPerShare : meta.riskReward ?? 0;
    const riskPercent = availableCash && riskAmount ? (riskAmount / availableCash) * 100 : 0;
    const brokerage = 0;
    const charges = 0;
    return {
      estimatedCost,
      riskPerShare,
      rewardPerShare,
      riskAmount,
      potentialProfit,
      potentialLoss,
      riskReward,
      riskPercent,
      brokerage,
      charges,
      totalCost: estimatedCost + brokerage + charges,
    };
  }, [ticket, entryReference, availableCash, meta.riskReward]);

  const loadQuoteAndAccount = useCallback(async (symbol: string, gen?: number) => {
    const canon = toCanonicalSymbol(symbol) || "INFY";
    const myGen = gen ?? loadGenRef.current;
    logPaperOrder("api_request", { kind: "quote+account", symbol: canon, gen: myGen });
    setQuoteStatus("loading");
    const [quote, acct] = await Promise.all([
      fetchPaperQuote(canon).catch((err) => {
        logPaperOrder("api_failure", {
          kind: "quote",
          symbol: canon,
          message: err instanceof Error ? err.message : String(err),
        });
        return null;
      }),
      fetchPaperAccountSummary({ force: true }).catch((err) => {
        logPaperOrder("api_failure", {
          kind: "account",
          message: err instanceof Error ? err.message : String(err),
        });
        return null;
      }),
    ]);
    if (myGen !== loadGenRef.current) return;

    if (quote?.current_price != null && Number(quote.current_price) > 0) {
      setCurrentPrice(Number(quote.current_price));
      setQuoteStatus(quote.is_stale ? "degraded" : "live");
      logPaperOrder("api_response", {
        kind: "quote",
        symbol: canon,
        price: Number(quote.current_price),
        status: quote.is_stale ? "degraded" : "live",
      });
    } else {
      setQuoteStatus("error");
      logPaperOrder("api_response", { kind: "quote", symbol: canon, price: null });
    }
    if (acct) {
      const cash = extractPaperAvailableCash(acct);
      const riskPct = extractPaperMaxRiskPerTrade(acct);
      setAvailableCash(cash);
      setMaxRiskPercent(riskPct);
      setAccountLoaded(true);
      logPaperCapital("paper-order", "account_loaded", acct, {
        symbol: canon,
        gen: myGen,
        resolved_available_cash: cash,
      });
      logPaperOrder("api_response", {
        kind: "account",
        available_cash: cash,
        balance: acct.balance ?? acct.cash_balance ?? null,
        available_funds: acct.available_funds ?? null,
      });
    } else {
      // Do not invent capital — leave cash null and mark load complete so UI can warn.
      setAccountLoaded(true);
      logPaperOrder("api_response", { kind: "account", available_cash: null, failed: true });
    }
  }, []);

  /**
   * Load ticket data for the current route/nav state.
   * `isActive` must stay true for the caller; Strict Mode / unmount sets it false
   * so we never leave isLoading stuck after a cancelled run.
   */
  const runBootstrap = useCallback(
    async (isActive: () => boolean, opts?: { forceSymbol?: string }) => {
      const gen = ++loadGenRef.current;
      logPaperOrder("loading_start", {
        gen,
        path: location.pathname,
        search: location.search,
        hasNavState,
        symbol: opts?.forceSymbol || initialSymbol || null,
        side: initialSide,
        orderId: orderIdFromUrl,
        hasPrefill: Boolean(navState.prefill),
      });
      if (!hasNavState && !searchParams.get("symbol") && !orderIdFromUrl) {
        logPaperOrder("missing_navigation_state", {
          search: location.search,
          note: "Falling back to URL/query or default symbol",
        });
      }

      setIsLoading(true);
      setAccountLoaded(false);
      setAvailableCash(null);
      setLoadError(null);
      setPageError(null);

      const symbolForLoad =
        toCanonicalSymbol(opts?.forceSymbol || initialSymbol) || DEFAULT_TICKET.symbol;

      try {
        await withTimeout(
          (async () => {
            if (orderIdFromUrl) {
              logPaperOrder("api_request", { kind: "pending-orders", orderId: orderIdFromUrl });
              const orders = await fetchPendingPaperOrders().catch((err) => {
                logPaperOrder("api_failure", {
                  kind: "pending-orders",
                  message: err instanceof Error ? err.message : String(err),
                });
                return [];
              });
              if (!isActive() || gen !== loadGenRef.current) return;

              const order = orders.find((o: { id: number }) => o.id === orderIdFromUrl);
              if (order) {
                setEditingOrderId(orderIdFromUrl);
                setTicket({
                  symbol: toCanonicalSymbol(order.symbol),
                  side: order.side,
                  type: order.type,
                  productType: order.product_type ?? "CNC",
                  qty: order.qty,
                  limitPrice: order.price ?? null,
                  stopPrice: order.stop_price ?? null,
                  stopLoss: order.stop_loss ?? null,
                  target: order.target ?? null,
                  notes: order.notes ?? "",
                  sourceSignal: order.source_signal ?? null,
                  sourceScore: order.source_score ?? null,
                  sourceConfidence: order.source_confidence ?? null,
                });
                setMeta({
                  signal: order.source_signal,
                  score: order.source_score,
                  confidence: order.source_confidence,
                  riskReward: null,
                });
                await loadQuoteAndAccount(order.symbol, gen);
              } else {
                logPaperOrder("loading_failure", {
                  reason: "order_not_found",
                  orderId: orderIdFromUrl,
                });
                setEditingOrderId(null);
                setPageError(`Pending order #${orderIdFromUrl} was not found. Showing a blank ticket.`);
                setTicket((t) => ({
                  ...t,
                  symbol: symbolForLoad,
                  side: initialSide,
                }));
                await loadQuoteAndAccount(symbolForLoad, gen);
              }
              return;
            }

            const prefill: RecommendationPrefillRequest | null | undefined = navState.prefill;
            if (prefill) {
              try {
                logPaperOrder("api_request", {
                  kind: "prefill",
                  symbol: prefill.symbol,
                });
                const result = await prefillPaperTrade(prefill);
                if (!isActive() || gen !== loadGenRef.current) return;
                logPaperOrder("api_response", {
                  kind: "prefill",
                  symbol: result.symbol,
                  qty: result.qty,
                  limit: result.limit_price,
                });
                setTicket({
                  symbol: toCanonicalSymbol(result.symbol),
                  side: result.side,
                  type: result.type,
                  productType: "CNC",
                  qty: result.qty,
                  limitPrice: result.limit_price ?? null,
                  stopPrice: null,
                  stopLoss: result.stop_loss ?? null,
                  target: result.target ?? null,
                  notes: result.note,
                  sourceSignal: String(prefill.recommendation_meta?.signal ?? "BUY"),
                  sourceScore: Number(prefill.recommendation_meta?.score ?? 0) || null,
                  sourceConfidence: Number(prefill.recommendation_meta?.confidence ?? 0) || null,
                });
                setMeta({
                  signal: String(prefill.recommendation_meta?.signal ?? "BUY"),
                  score: Number(prefill.recommendation_meta?.score ?? 0) || null,
                  confidence: Number(prefill.recommendation_meta?.confidence ?? 0) || null,
                  riskReward: navState.riskReward ?? null,
                });
                await loadQuoteAndAccount(result.symbol, gen);
              } catch (e) {
                if (!isActive() || gen !== loadGenRef.current) return;
                // Soft-fail: keep nav prefill fields so the page still works
                logPaperOrder("loading_failure", {
                  reason: "prefill_failed",
                  message: e instanceof Error ? e.message : String(e),
                });
                setTicket((t) => ({
                  ...t,
                  symbol: toCanonicalSymbol(prefill.symbol) || t.symbol,
                  limitPrice: prefill.suggested_entry ?? t.limitPrice,
                  stopLoss: prefill.suggested_stop ?? t.stopLoss,
                  target: prefill.suggested_targets?.[0] ?? t.target,
                  notes: "Scanner recommendation (offline prefill)",
                }));
                if (prefill.suggested_entry) setCurrentPrice(prefill.suggested_entry);
                setQuoteStatus("degraded");
                setPageError(
                  e instanceof Error
                    ? `Scanner prefill unavailable: ${e.message}`
                    : "Scanner data unavailable. Edit fields manually.",
                );
                await loadQuoteAndAccount(prefill.symbol, gen);
              }
              return;
            }

            // No prefill / no edit — load by symbol (URL query or nav state)
            if (!symbolForLoad) {
              setLoadError("Unable to load order details. No symbol was provided.");
              setQuoteStatus("error");
              return;
            }

            setTicket((t) => ({
              ...t,
              symbol: symbolForLoad,
              side: initialSide,
              limitPrice: t.limitPrice ?? navState.currentPrice ?? null,
              sourceSignal: (navState.signal as string) ?? t.sourceSignal ?? initialSide,
              sourceScore: navState.score ?? t.sourceScore,
              sourceConfidence: navState.confidence ?? t.sourceConfidence,
            }));
            setMeta((m) => ({
              signal: navState.signal ?? m.signal ?? initialSide,
              score: navState.score ?? m.score,
              confidence: navState.confidence ?? m.confidence,
              riskReward: navState.riskReward ?? m.riskReward,
            }));
            await loadQuoteAndAccount(symbolForLoad, gen);
          })(),
          BOOTSTRAP_TIMEOUT_MS,
          "Order ticket bootstrap",
        );
      } catch (e) {
        if (!isActive() || gen !== loadGenRef.current) return;
        const msg = e instanceof Error ? e.message : "Unable to load order details.";
        logPaperOrder("loading_failure", { reason: "bootstrap_error", message: msg, gen });
        setLoadError(msg);
        // Soft recovery: still show form with whatever we have
        setTicket((t) => ({
          ...t,
          symbol: symbolForLoad || t.symbol,
          side: initialSide,
          limitPrice: t.limitPrice ?? navState.currentPrice ?? null,
        }));
        if (navState.currentPrice != null) {
          setCurrentPrice(navState.currentPrice);
          setQuoteStatus("degraded");
        } else {
          setQuoteStatus("error");
        }
      } finally {
        // Critical: only the active effect/retry may clear loading.
        // Strict Mode cancels the first run; the second run always clears.
        if (isActive() && gen === loadGenRef.current) {
          setIsLoading(false);
          logPaperOrder("loading_complete", {
            gen,
            symbol: symbolForLoad,
            hasPrefill: Boolean(navState.prefill),
          });
        }
      }
    },
    // Closures read latest nav/location; effect below re-runs on URL identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      initialSymbol,
      initialSide,
      orderIdFromUrl,
      hasNavState,
      location.pathname,
      location.search,
      loadQuoteAndAccount,
    ],
  );

  // Initial load + re-load when URL identity changes.
  // Strict Mode safe: each effect instance has its own `active` flag.
  // The previous anti-pattern (loadedRef early-return) skipped the remount
  // run after cancelling the first — leaving isLoading stuck at true forever.
  useEffect(() => {
    let active = true;
    const isActive = () => active;

    logPaperOrder("navigation", {
      pathname: location.pathname,
      search: location.search,
      symbol: initialSymbol || null,
      side: initialSide,
      hasNavState,
      orderId: orderIdFromUrl,
    });

    void runBootstrap(isActive);

    return () => {
      active = false;
      loadGenRef.current += 1;
      pollAbortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.search, orderIdFromUrl, initialSymbol, initialSide, runBootstrap]);

  function handleRetry() {
    setLoadError(null);
    setPageError(null);
    void runBootstrap(() => true, { forceSymbol: ticket.symbol || initialSymbol });
  }

  // Live quote poll while on the page (cancelled on leave / symbol change)
  useEffect(() => {
    const sym = toCanonicalSymbol(ticket.symbol);
    if (!sym || isLoading) return;

    pollAbortRef.current?.abort();
    const ac = new AbortController();
    pollAbortRef.current = ac;

    const id = window.setInterval(() => {
      if (ac.signal.aborted) return;
      void fetchPaperQuote(sym)
        .then((q) => {
          if (ac.signal.aborted) return;
          if (q?.current_price != null && Number(q.current_price) > 0) {
            setCurrentPrice(Number(q.current_price));
            setQuoteStatus(q.is_stale ? "degraded" : "live");
          }
        })
        .catch(() => {
          if (!ac.signal.aborted) {
            setQuoteStatus((s) => (s === "live" ? "degraded" : s));
          }
        });
    }, QUOTE_POLL_MS);

    return () => {
      ac.abort();
      window.clearInterval(id);
    };
  }, [ticket.symbol, isLoading]);

  function handleBack() {
    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate(returnTo || "/scanner");
    }
  }

  /**
   * Full frontend validation for Place Paper Order.
   * Returns structured PASS/FAIL results + field errors with concrete values.
   * Never collapses failures into a single generic message at the call site.
   */
  function validateTicket(): {
    ok: boolean;
    errors: Record<string, string>;
    messages: string[];
    results: Array<{ rule: string; status: "PASS" | "FAIL" | "SKIP"; detail?: string }>;
  } {
    const errors: Record<string, string> = {};
    const results: Array<{ rule: string; status: "PASS" | "FAIL" | "SKIP"; detail?: string }> = [];
    const qty = Number(ticket.qty);
    const entry = entryReference != null && entryReference > 0 ? entryReference : null;
    const entryLabel = entry != null ? formatInr(entry) : "—";

    // Symbol
    if (!ticket.symbol?.trim()) {
      errors.symbol = "Symbol is required.";
      results.push({ rule: "Symbol", status: "FAIL", detail: errors.symbol });
    } else {
      results.push({ rule: "Symbol", status: "PASS", detail: ticket.symbol });
    }

    // Side / Type / Product — informational (always valid enums from selects)
    results.push({ rule: "Side", status: "PASS", detail: ticket.side });
    results.push({ rule: "Order Type", status: "PASS", detail: ticket.type });
    results.push({
      rule: "Product",
      status: "PASS",
      detail: ticket.productType ?? "CNC",
    });

    // Quantity
    if (!Number.isFinite(qty) || qty < 1) {
      errors.qty = "Quantity must be at least 1.";
      results.push({ rule: "Quantity", status: "FAIL", detail: errors.qty });
    } else {
      results.push({ rule: "Quantity", status: "PASS", detail: String(qty) });
    }

    // Limit / stop trigger price
    if (ticket.type !== "MARKET") {
      const priceField = ticket.type === "STOP" ? ticket.stopPrice : ticket.limitPrice;
      const priceName =
        ticket.type === "STOP" || ticket.type === "STOP_LIMIT" ? "Stop Trigger" : "Limit Price";
      if (priceField == null || priceField <= 0) {
        errors.price = `${priceName} is required and must be greater than 0.`;
        results.push({ rule: priceName, status: "FAIL", detail: errors.price });
      } else {
        results.push({
          rule: priceName,
          status: "PASS",
          detail: formatInr(priceField),
        });
      }
    } else {
      results.push({ rule: "Limit Price", status: "SKIP", detail: "Not required for MARKET" });
    }

    // Entry reference used for SL/Target rules
    if (entry == null) {
      results.push({
        rule: "Entry Price",
        status: "FAIL",
        detail: "Entry price is unavailable. Set limit/stop price or wait for a live quote.",
      });
      if (!errors.price) {
        errors.price =
          "Entry price is unavailable. Set a limit/stop price or wait for a live quote before placing.";
      }
    } else {
      results.push({ rule: "Entry Price", status: "PASS", detail: entryLabel });
    }

    // Stop Loss vs Entry (BUY: SL < entry; SELL: SL > entry)
    if (ticket.stopLoss == null) {
      results.push({ rule: "Stop Loss", status: "SKIP", detail: "Optional — not set" });
    } else if (entry == null) {
      results.push({
        rule: "Stop Loss",
        status: "SKIP",
        detail: "Skipped — entry price unavailable",
      });
    } else if (ticket.side === "BUY" && ticket.stopLoss >= entry) {
      errors.stopLoss = `Stop Loss (${formatInr(ticket.stopLoss)}) must be below Entry Price (${entryLabel}) for BUY.`;
      results.push({ rule: "Stop Loss", status: "FAIL", detail: errors.stopLoss });
    } else if (ticket.side === "SELL" && ticket.stopLoss <= entry) {
      errors.stopLoss = `Stop Loss (${formatInr(ticket.stopLoss)}) must be above Entry Price (${entryLabel}) for SELL.`;
      results.push({ rule: "Stop Loss", status: "FAIL", detail: errors.stopLoss });
    } else {
      results.push({
        rule: "Stop Loss",
        status: "PASS",
        detail: `${formatInr(ticket.stopLoss)} vs entry ${entryLabel} (${ticket.side})`,
      });
    }

    // Target vs Entry (BUY: target > entry; SELL: target < entry)
    if (ticket.target == null) {
      results.push({ rule: "Target", status: "SKIP", detail: "Optional — not set" });
    } else if (entry == null) {
      results.push({
        rule: "Target",
        status: "SKIP",
        detail: "Skipped — entry price unavailable",
      });
    } else if (ticket.side === "BUY" && ticket.target <= entry) {
      errors.target = `Target (${formatInr(ticket.target)}) must be above Entry Price (${entryLabel}) for BUY.`;
      results.push({ rule: "Target", status: "FAIL", detail: errors.target });
    } else if (ticket.side === "SELL" && ticket.target >= entry) {
      errors.target = `Target (${formatInr(ticket.target)}) must be below Entry Price (${entryLabel}) for SELL.`;
      results.push({ rule: "Target", status: "FAIL", detail: errors.target });
    } else {
      results.push({
        rule: "Target",
        status: "PASS",
        detail: `${formatInr(ticket.target)} vs entry ${entryLabel} (${ticket.side})`,
      });
    }

    // Available cash (BUY only) — never treat "not loaded" as ₹0
    if (ticket.side !== "BUY") {
      results.push({
        rule: "Available Cash",
        status: "SKIP",
        detail: "Cash check applies to BUY only",
      });
    } else if (!accountLoaded || availableCash == null) {
      errors.cash = "Paper account capital is still loading. Wait a moment and try again.";
      results.push({ rule: "Available Cash", status: "FAIL", detail: errors.cash });
    } else if (risk.estimatedCost > availableCash + 0.01) {
      errors.cash = `Estimated cost ${formatInr(risk.estimatedCost)} exceeds available cash ${formatInr(availableCash)}.`;
      results.push({
        rule: "Available Cash",
        status: "FAIL",
        detail: errors.cash,
      });
    } else {
      results.push({
        rule: "Available Cash",
        status: "PASS",
        detail: `Cost ${formatInr(risk.estimatedCost)} ≤ cash ${formatInr(availableCash)}`,
      });
    }

    // Risk % of account (when SL is set so riskAmount > 0)
    if (!accountLoaded) {
      results.push({
        rule: "Risk %",
        status: "SKIP",
        detail: "Account not loaded yet",
      });
    } else if (!(risk.riskAmount > 0)) {
      results.push({
        rule: "Risk %",
        status: "SKIP",
        detail: "No stop-loss risk amount to evaluate",
      });
    } else if (risk.riskPercent > maxRiskPercent * 100 + 0.01) {
      errors.risk = `Risk ${risk.riskPercent.toFixed(2)}% of account exceeds guideline ${(maxRiskPercent * 100).toFixed(1)}% (risk amount ${formatInr(risk.riskAmount)}).`;
      results.push({ rule: "Risk %", status: "FAIL", detail: errors.risk });
    } else {
      results.push({
        rule: "Risk %",
        status: "PASS",
        detail: `${risk.riskPercent.toFixed(2)}% ≤ ${(maxRiskPercent * 100).toFixed(1)}% guideline`,
      });
    }

    // Cash allocation helper is optional UI only — not a hard order field
    results.push({
      rule: "Cash Allocation",
      status: "SKIP",
      detail: "Helper only — not a placement constraint",
    });

    const messages = Object.values(errors);
    const ok = messages.length === 0;

    logPaperOrder("validation_result", {
      ok,
      side: ticket.side,
      type: ticket.type,
      qty,
      entry,
      stopLoss: ticket.stopLoss,
      target: ticket.target,
      availableCash,
      estimatedCost: risk.estimatedCost,
      riskPercent: risk.riskPercent,
      maxRiskPercent,
      results,
      errors,
    });
    console.info(
      "[paper-order] Validation:\n" +
        results.map((r) => `${r.rule}: ${r.status}${r.detail ? ` — ${r.detail}` : ""}`).join("\n"),
    );

    setFieldErrors(errors);
    return { ok, errors, messages, results };
  }

  function handlePlaceClick() {
    if (!accountLoaded || (ticket.side === "BUY" && availableCash == null)) {
      toast.error("Loading paper account", "Available cash is still loading. Please wait.");
      return;
    }

    const validation = validateTicket();
    if (!validation.ok) {
      const title =
        validation.messages.length === 1
          ? "Order validation failed"
          : `${validation.messages.length} validation errors`;
      const summary =
        validation.messages.length === 1
          ? validation.messages[0]
          : validation.messages.map((m, i) => `${i + 1}. ${m}`).join(" ");
      // Title + every exact failure — never a generic-only "Fix validation errors" toast.
      toast.toast(title, {
        level: "error",
        description: summary,
        duration: Math.min(14_000, 6_000 + validation.messages.length * 2_500),
        dedupeKey: "paper-order-validation",
      });
      // Persistent on-page alert so failures remain after the toast dismisses.
      setPageError(
        validation.messages.length === 1
          ? validation.messages[0]
          : `Cannot place order:\n${validation.messages.map((m) => `• ${m}`).join("\n")}`,
      );
      return;
    }

    setPageError(null);
    setConfirmOpen(true);
  }

  async function handleConfirmOrder() {
    setIsSubmitting(true);
    setPageError(null);
    try {
      const normalized: PaperOrderTicketState = {
        ...ticket,
        symbol: toCanonicalSymbol(ticket.symbol),
      };

      if (editingOrderId) {
        await updatePaperOrder(editingOrderId, {
          qty: normalized.qty,
          limit_price: normalized.limitPrice,
          stop_price: normalized.stopPrice,
          stop_loss: normalized.stopLoss,
          target: normalized.target,
          type: normalized.type,
          product_type: normalized.productType,
        } as Partial<PaperOrderTicketState> & Record<string, unknown>);
        toast.success("✓ Paper Order Updated Successfully");
      } else {
        const response = await placePaperOrder(normalized, idempotencyKey);
        setIdempotencyKey(crypto.randomUUID());
        const orderStatus = response.order?.status;
        if (orderStatus === "PENDING_MARKET_OPEN") {
          toast.success(
            "Order accepted",
            "The market is currently closed. Your order has been placed successfully and will be executed automatically when the market opens.",
          );
        } else if (orderStatus === "FILLED" || orderStatus === "EXECUTED") {
          toast.success(
            `Your ${normalized.side} order for ${normalized.symbol} has been executed successfully.`,
            response.position
              ? "Position has been added to your portfolio."
              : response.message || "Order filled.",
          );
        } else {
          toast.success("✓ Paper Order Placed Successfully", response.message || undefined);
        }
      }

      invalidatePaperCaches();
      setConfirmOpen(false);

      navigate("/paper", {
        replace: false,
        state: { orderJustPlaced: true, symbol: normalized.symbol },
      });
      window.dispatchEvent(
        new CustomEvent("paper:order-success", {
          detail: { symbol: normalized.symbol },
        }),
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to place order.";
      setPageError(msg);
      toast.error("Order failed", msg);
    } finally {
      setIsSubmitting(false);
    }
  }

  function applyTrailingStop() {
    const pct = Number(trailingStopPct) || 0;
    if (!entryReference || pct <= 0) return;
    const direction = ticket.side === "BUY" ? -1 : 1;
    setTicket({
      ...ticket,
      stopLoss: Math.round(entryReference * (1 + (direction * pct) / 100) * 20) / 20,
    });
  }

  function applyCashAllocation() {
    const pct = Number(cashAllocPct) || 0;
    if (!availableCash || !entryReference || pct <= 0) return;
    const qty = Math.max(1, Math.floor((availableCash * (pct / 100)) / entryReference));
    setTicket({ ...ticket, qty });
  }

  const signalLabel = String(meta.signal || ticket.sourceSignal || ticket.side || "—");
  const signalClass =
    signalLabel.toUpperCase() === "BUY"
      ? "paper-order-badge paper-order-badge--buy"
      : signalLabel.toUpperCase() === "SELL"
        ? "paper-order-badge paper-order-badge--sell"
        : "paper-order-badge";

  const showHardLoadError = Boolean(loadError) && !isLoading;
  const quoteUnavailable = quoteStatus === "error" && !isLoading;

  return (
    <main className="page-container page-container--wide paper-order-page" data-testid="paper-order-page">
      <header className="paper-order-page__header">
        <div className="paper-order-page__header-left">
          <button
            type="button"
            className="button ghost-button paper-order-page__back"
            onClick={handleBack}
            data-testid="paper-order-back"
          >
            ← Back
          </button>
          <div>
            <p className="section-label">Paper Trading</p>
            <h1 className="paper-order-page__title">
              {editingOrderId ? "Edit Paper Order" : "Paper Order"}
            </h1>
          </div>
        </div>
        <div className="paper-order-page__header-meta">
          <span className={signalClass}>{signalLabel}</span>
          <span
            className={`helper-chip ${quoteStatus === "live" ? "" : "is-risk"}`}
            title={quoteStatus}
          >
            {quoteStatus === "live"
              ? "Live Market Connected"
              : quoteStatus === "loading"
                ? "Connecting…"
                : quoteStatus === "degraded"
                  ? "Degraded quote"
                  : "Quote unavailable"}
          </span>
        </div>
      </header>

      {isLoading ? (
        <section className="panel paper-order-page__loading" aria-busy="true">
          <p className="muted-copy">Loading order ticket…</p>
        </section>
      ) : null}

      {showHardLoadError ? (
        <section className="panel error-state" role="alert" data-testid="paper-order-load-error">
          <h2 className="ds-title">Unable to load order details</h2>
          <p className="muted-copy">{loadError}</p>
          <div style={{ display: "flex", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
            <Button variant="primary" onClick={handleRetry} data-testid="paper-order-retry">
              Retry
            </Button>
            <Button variant="ghost" onClick={handleBack}>
              Back
            </Button>
          </div>
          <p className="helper-text" style={{ marginTop: 12 }}>
            You can still edit the ticket below with any values already known from navigation.
          </p>
        </section>
      ) : null}

      {quoteUnavailable && !showHardLoadError ? (
        <div className="warning-box panel" role="status" style={{ marginBottom: 12 }}>
          <p>
            <strong>Unable to load latest market data.</strong>{" "}
            {navState.currentPrice != null || ticket.limitPrice != null
              ? "Using scanner / last known price where available."
              : "Enter limit price manually or retry."}
          </p>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button type="button" className="button ghost-button" onClick={handleRetry}>
              Retry
            </button>
          </div>
        </div>
      ) : null}

      {!isLoading ? (
        <div className="paper-order-layout">
          {/* Stock summary */}
          <section className="panel paper-order-summary">
            <div className="paper-order-summary__top">
              <div>
                <p className="section-label">Stock</p>
                <h2 className="paper-order-summary__symbol">{ticket.symbol || "—"}</h2>
              </div>
              <div className="paper-order-summary__price-block">
                <p className="section-label">Current / Live</p>
                <div className="paper-order-summary__price">
                  {currentPrice != null ? `₹${currentPrice.toFixed(2)}` : "—"}
                </div>
              </div>
            </div>
            <div className="paper-order-summary__metrics">
              <Metric label="Signal" value={signalLabel} />
              <Metric
                label="Score"
                value={meta.score != null && meta.score !== 0 ? formatNum(Number(meta.score), 1) : "—"}
              />
              <Metric
                label="Confidence"
                value={
                  meta.confidence != null && Number(meta.confidence) > 0
                    ? Number(meta.confidence) <= 1
                      ? `${Math.round(Number(meta.confidence) * 100)}%`
                      : `${Math.round(Number(meta.confidence))}%`
                    : "—"
                }
              />
              <Metric
                label="Risk / Reward"
                value={risk.riskReward ? formatNum(risk.riskReward, 2) : "—"}
              />
            </div>
            {navState.prefill ? (
              <p className="helper-text" style={{ marginTop: 12 }}>
                Scanner recommendation loaded
                {navState.prefill.suggested_entry != null
                  ? ` · suggested entry ${formatInr(navState.prefill.suggested_entry)}`
                  : ""}
                {ticket.qty ? ` · suggested qty ${ticket.qty}` : ""}.
              </p>
            ) : !hasNavState && searchParams.get("symbol") ? (
              <p className="helper-text" style={{ marginTop: 12 }}>
                Loaded from symbol (scanner data not in navigation state).
              </p>
            ) : null}
          </section>

          {/* Order details form */}
          <section className="panel paper-order-form">
            <h3 className="paper-order-section-title">Order Details</h3>
            <div className="paper-ticket-grid">
              <label className="filter-field">
                <span>
                  Symbol
                  <InfoTooltip content="Cash equity symbol (canonical form)" />
                </span>
                <input
                  data-testid="paper-order-symbol"
                  value={ticket.symbol}
                  onChange={(e) => {
                    const sym = toCanonicalSymbol(e.target.value) || e.target.value.toUpperCase();
                    setTicket({ ...ticket, symbol: sym });
                  }}
                  onBlur={() => {
                    if (ticket.symbol) void loadQuoteAndAccount(ticket.symbol);
                  }}
                />
                {fieldErrors.symbol ? <span className="field-error">{fieldErrors.symbol}</span> : null}
              </label>

              <label className="filter-field">
                <span>Side</span>
                <select
                  data-testid="paper-order-side"
                  value={ticket.side}
                  onChange={(e) => setTicket({ ...ticket, side: e.target.value as "BUY" | "SELL" })}
                >
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
              </label>

              <label className="filter-field">
                <span>
                  Order Type
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.ORDER_TYPE} />
                </span>
                <select
                  data-testid="paper-order-type"
                  value={ticket.type}
                  onChange={(e) => setTicket({ ...ticket, type: e.target.value as PaperOrderTicketState["type"] })}
                >
                  <option value="MARKET">Market</option>
                  <option value="LIMIT">Limit</option>
                  <option value="STOP">Stop-Loss</option>
                  <option value="STOP_LIMIT">Stop-Limit</option>
                  <option value="GTT">GTT</option>
                </select>
              </label>

              <label className="filter-field">
                <span>
                  Product
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.PRODUCT_TYPE} />
                </span>
                <select
                  value={ticket.productType ?? "CNC"}
                  onChange={(e) =>
                    setTicket({
                      ...ticket,
                      productType: e.target.value as PaperOrderTicketState["productType"],
                    })
                  }
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
                  data-testid="paper-order-qty"
                  type="number"
                  min={1}
                  value={ticket.qty}
                  onChange={(e) => setTicket({ ...ticket, qty: Number(e.target.value) })}
                />
                {fieldErrors.qty ? <span className="field-error">{fieldErrors.qty}</span> : null}
              </label>

              {ticket.type !== "MARKET" ? (
                <label className="filter-field">
                  <span>
                    {ticket.type === "STOP" || ticket.type === "STOP_LIMIT" ? "Stop Trigger" : "Limit Price"}
                    <InfoTooltip content={TOOLTIPS.PAPER_TRADING.LIMIT_PRICE} />
                  </span>
                  <input
                    data-testid="paper-order-price"
                    type="number"
                    min={0.01}
                    step="0.05"
                    value={
                      ticket.type === "STOP"
                        ? ticket.stopPrice ?? ""
                        : ticket.limitPrice ?? ""
                    }
                    onChange={(e) => {
                      const v = Number(e.target.value) || null;
                      if (ticket.type === "STOP") setTicket({ ...ticket, stopPrice: v });
                      else setTicket({ ...ticket, limitPrice: v });
                    }}
                  />
                  {fieldErrors.price ? <span className="field-error">{fieldErrors.price}</span> : null}
                </label>
              ) : null}

              <label className="filter-field">
                <span>
                  Stop Loss
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.STOP_LOSS_FIELD} />
                </span>
                <input
                  data-testid="paper-order-sl"
                  type="number"
                  min={0.01}
                  step="0.05"
                  value={ticket.stopLoss ?? ""}
                  onChange={(e) => {
                    setTicket({ ...ticket, stopLoss: Number(e.target.value) || null });
                    setFieldErrors((prev) => {
                      if (!prev.stopLoss) return prev;
                      const next = { ...prev };
                      delete next.stopLoss;
                      return next;
                    });
                    setPageError(null);
                  }}
                />
                {fieldErrors.stopLoss ? (
                  <span className="field-error" data-testid="paper-order-sl-error">
                    {fieldErrors.stopLoss}
                  </span>
                ) : null}
              </label>

              <label className="filter-field">
                <span>
                  Target
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TARGET_FIELD} />
                </span>
                <input
                  data-testid="paper-order-target"
                  type="number"
                  min={0.01}
                  step="0.05"
                  value={ticket.target ?? ""}
                  onChange={(e) => {
                    setTicket({ ...ticket, target: Number(e.target.value) || null });
                    setFieldErrors((prev) => {
                      if (!prev.target) return prev;
                      const next = { ...prev };
                      delete next.target;
                      return next;
                    });
                    setPageError(null);
                  }}
                />
                {fieldErrors.target ? (
                  <span className="field-error" data-testid="paper-order-target-error">
                    {fieldErrors.target}
                  </span>
                ) : null}
              </label>
            </div>

            <div className="broker-helper-grid" style={{ marginTop: 16 }}>
              <label className="filter-field">
                <span>
                  Trailing Stop %
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.TRAILING_STOP} />
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="number"
                    min={0.1}
                    step="0.1"
                    value={trailingStopPct}
                    onChange={(e) => setTrailingStopPct(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button type="button" className="button ghost-button" onClick={applyTrailingStop}>
                    Apply
                  </button>
                </div>
              </label>
              <label className="filter-field">
                <span>
                  Cash Allocation %
                  <InfoTooltip content={TOOLTIPS.PAPER_TRADING.CASH_ALLOCATION} />
                </span>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={cashAllocPct}
                    onChange={(e) => setCashAllocPct(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button type="button" className="button ghost-button" onClick={applyCashAllocation}>
                    Apply
                  </button>
                </div>
              </label>
            </div>

            <label className="filter-field" style={{ marginTop: 16 }}>
              <span>Notes</span>
              <input
                data-testid="paper-order-notes"
                value={ticket.notes ?? ""}
                onChange={(e) => setTicket({ ...ticket, notes: e.target.value })}
              />
            </label>
          </section>

          {/* Risk summary */}
          <section className="panel paper-order-risk">
            <h3 className="paper-order-section-title">Risk Summary</h3>
            <div className="paper-order-risk__grid">
              <Metric label="Estimated Cost" value={formatInr(risk.estimatedCost)} />
              <Metric
                label="Available Cash"
                value={
                  !accountLoaded
                    ? "Loading…"
                    : availableCash == null
                      ? "Unavailable"
                      : formatInr(availableCash)
                }
              />
              <Metric label="Risk Amount" value={formatInr(risk.riskAmount)} />
              <Metric label="Potential Profit" value={formatInr(risk.potentialProfit)} />
              <Metric label="Potential Loss" value={formatInr(risk.potentialLoss)} />
              <Metric label="Brokerage" value={formatInr(risk.brokerage)} />
              <Metric label="Charges" value={formatInr(risk.charges)} />
              <Metric label="Risk % of Account" value={`${risk.riskPercent.toFixed(2)}%`} />
            </div>
            {fieldErrors.cash ? (
              <div className="warning-box" style={{ marginTop: 12 }} data-testid="paper-order-cash-error">
                <p>{fieldErrors.cash}</p>
              </div>
            ) : null}
            {fieldErrors.risk ? (
              <div className="warning-box" style={{ marginTop: 12 }} data-testid="paper-order-risk-error">
                <p>{fieldErrors.risk}</p>
              </div>
            ) : null}
            <p className="helper-text" style={{ marginTop: 12 }}>
              Guideline: risk no more than {(maxRiskPercent * 100).toFixed(1)}% per trade. Prefer setups with at
              least 1:2 risk-reward. Paper trading only — no real capital is used.
            </p>
          </section>
        </div>
      ) : null}

      {pageError || Object.keys(fieldErrors).length > 0 ? (
        <div
          className="error-state panel"
          role="alert"
          data-testid="paper-order-validation-summary"
          style={{ marginTop: 16, whiteSpace: "pre-line" }}
        >
          <strong style={{ display: "block", marginBottom: 8 }}>
            {Object.keys(fieldErrors).length > 1
              ? `${Object.keys(fieldErrors).length} validation issues — fix all of the following:`
              : "Validation issue — fix the following:"}
          </strong>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {(pageError
              ? pageError
                  .replace(/^Cannot place order:\n?/, "")
                  .split("\n")
                  .map((line) => line.replace(/^[•\-\d.]+\s*/, "").trim())
                  .filter(Boolean)
              : Object.values(fieldErrors)
            ).map((msg) => (
              <li key={msg}>{msg}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Sticky actions */}
      <div className="paper-order-page__actions" data-testid="paper-order-actions">
        <Button variant="ghost" onClick={handleBack} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button
          variant="primary"
          onClick={handlePlaceClick}
          disabled={isLoading || isSubmitting}
          data-testid="paper-order-place"
        >
          Place Paper Order
        </Button>
      </div>

      {/* Confirmation modal — only executes after Confirm */}
      <Modal
        open={confirmOpen}
        onClose={() => {
          if (!isSubmitting) setConfirmOpen(false);
        }}
        title="Confirm Paper Order"
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => void handleConfirmOrder()}
              loading={isSubmitting}
              disabled={isSubmitting}
              data-testid="paper-order-confirm"
            >
              Confirm Order
            </Button>
          </>
        }
      >
        <div className="paper-order-confirm" data-testid="paper-order-confirm-body">
          <p className="paper-order-confirm__lead">
            You are about to <strong>{ticket.side}</strong>
          </p>
          <p className="paper-order-confirm__qty">
            <strong>{ticket.qty}</strong> share{ticket.qty === 1 ? "" : "s"} of{" "}
            <strong>
              {ticket.symbol}
              {ticket.symbol && !ticket.symbol.includes("-") ? "-EQ" : ""}
            </strong>
          </p>
          <dl className="paper-order-confirm__dl">
            <div>
              <dt>Price</dt>
              <dd>{formatInr(entryReference)}</dd>
            </div>
            <div>
              <dt>Estimated Cost</dt>
              <dd>{formatInr(risk.estimatedCost)}</dd>
            </div>
            <div>
              <dt>Brokerage</dt>
              <dd>{formatInr(risk.brokerage)}</dd>
            </div>
            <div>
              <dt>Order Type</dt>
              <dd>{ticket.type}</dd>
            </div>
            {ticket.stopLoss != null ? (
              <div>
                <dt>Stop Loss</dt>
                <dd>{formatInr(ticket.stopLoss)}</dd>
              </div>
            ) : null}
            {ticket.target != null ? (
              <div>
                <dt>Target</dt>
                <dd>{formatInr(ticket.target)}</dd>
              </div>
            ) : null}
          </dl>
          <div className="paper-order-confirm__notice">
            <strong>Paper Trading</strong>
            <p>This order will affect your paper portfolio only. No real money will be used.</p>
          </div>
        </div>
      </Modal>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default PaperOrderPage;

/**
 * Shared Paper Trading capital helpers.
 *
 * Paper Desk and Paper Order must read available cash from the same semantic
 * fields. Backend GET /paper-trading/account/summary is the compact source of
 * truth and always includes available_cash (+ aliases).
 */

export type PaperCapitalSource = {
  available_cash?: number | null;
  available_funds?: number | null;
  balance?: number | null;
  cash_balance?: number | null;
  equity?: number | null;
  starting_balance?: number | null;
  reserved_cash?: number | null;
  total_invested?: number | null;
  invested_value?: number | null;
  max_risk_per_trade?: number | null;
  total_capital?: number | null;
  account?: PaperCapitalSource | null;
} | null | undefined;

function toFiniteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Unwrap nested `{ account: {...} }` dashboard payloads. */
export function unwrapPaperAccount(source: PaperCapitalSource): PaperCapitalSource {
  if (!source || typeof source !== "object") return source;
  if (source.account && typeof source.account === "object") {
    return source.account;
  }
  return source;
}

/**
 * Resolve available cash for order validation and display.
 * Preference order matches backend order-placement semantics:
 * available_cash (cash − reserved) → available_funds → balance → cash_balance.
 */
export function extractPaperAvailableCash(source: PaperCapitalSource): number | null {
  const acct = unwrapPaperAccount(source);
  if (!acct) return null;
  const candidates = [
    acct.available_cash,
    acct.available_funds,
    acct.balance,
    acct.cash_balance,
  ];
  for (const c of candidates) {
    const n = toFiniteNumber(c);
    if (n != null) return n;
  }
  return null;
}

/** Resolve max risk per trade fraction (e.g. 0.02 = 2%). Defaults to 0.02. */
export function extractPaperMaxRiskPerTrade(source: PaperCapitalSource, fallback = 0.02): number {
  const acct = unwrapPaperAccount(source);
  const n = toFiniteNumber(acct?.max_risk_per_trade);
  return n != null && n > 0 ? n : fallback;
}

/** Structured console log for capital diagnostics (Desk + Order). */
export function logPaperCapital(
  screen: "paper-desk" | "paper-order" | "order-drawer" | "account-panel" | "api",
  event: string,
  source: PaperCapitalSource,
  extra?: Record<string, unknown>,
): void {
  const acct = unwrapPaperAccount(source);
  const availableCash = extractPaperAvailableCash(source);
  console.info(`[paper-capital] ${screen} ${event}`, {
    available_cash: availableCash,
    available_funds: toFiniteNumber(acct?.available_funds),
    balance: toFiniteNumber(acct?.balance ?? acct?.cash_balance),
    equity: toFiniteNumber(acct?.equity),
    reserved_cash: toFiniteNumber(acct?.reserved_cash),
    max_risk_per_trade: extractPaperMaxRiskPerTrade(source),
    raw_keys: acct && typeof acct === "object" ? Object.keys(acct) : [],
    ...extra,
  });
}

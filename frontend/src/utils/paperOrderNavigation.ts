import type { NavigateFunction } from "react-router-dom";
import type { RecommendationPrefillRequest } from "../types";
import type { PaperOrderNavState } from "../types/paperOrderNav";

/** Canonical cash symbol for paper trading APIs. */
export function toCanonicalSymbol(raw: string | undefined | null): string {
  if (!raw) return "";
  let s = raw.trim().toUpperCase();
  if (s.startsWith("NSE:")) s = s.slice(4);
  else if (s.startsWith("BSE:")) s = s.slice(4);
  else if (s.includes(":")) s = s.split(":")[1] ?? s;
  if (s.endsWith("-EQ")) s = s.slice(0, -3);
  return s;
}

export type OpenPaperOrderOptions = {
  symbol?: string;
  side?: "BUY" | "SELL";
  prefill?: RecommendationPrefillRequest | null;
  orderId?: number | null;
  returnTo?: string;
  currentPrice?: number | null;
  signal?: string | null;
  score?: number | null;
  confidence?: number | null;
  riskReward?: number | null;
};

/**
 * Navigate to the dedicated full-page Paper Order ticket.
 * Prefer this over drawers/overlays for BUY/SELL placement.
 */
export function navigateToPaperOrder(
  navigate: NavigateFunction,
  options: OpenPaperOrderOptions = {},
): void {
  const symbol = toCanonicalSymbol(options.symbol || options.prefill?.symbol || "");
  const side = options.side ?? "BUY";
  const returnTo =
    options.returnTo ??
    (typeof window !== "undefined"
      ? `${window.location.pathname}${window.location.search || ""}`
      : "/scanner");

  const state: PaperOrderNavState = {
    symbol: symbol || undefined,
    side,
    prefill: options.prefill ?? null,
    orderId: options.orderId ?? null,
    returnTo,
    currentPrice: options.currentPrice ?? null,
    signal: options.signal ?? (options.prefill?.recommendation_meta?.signal as string | undefined) ?? null,
    score:
      options.score ??
      (typeof options.prefill?.recommendation_meta?.score === "number"
        ? Number(options.prefill.recommendation_meta.score)
        : null),
    confidence:
      options.confidence ??
      (typeof options.prefill?.recommendation_meta?.confidence === "number"
        ? Number(options.prefill.recommendation_meta.confidence)
        : null),
    riskReward: options.riskReward ?? null,
  };

  const params = new URLSearchParams();
  if (symbol) params.set("symbol", symbol);
  params.set("side", side);
  if (options.orderId) params.set("orderId", String(options.orderId));
  const qs = params.toString();

  navigate(`/paper-order${qs ? `?${qs}` : ""}`, { state });
}

/** Dispatch-friendly open (works from pages without navigate in scope). */
export function dispatchOpenPaperOrder(options: OpenPaperOrderOptions = {}): void {
  try {
    window.dispatchEvent(
      new CustomEvent("paper:open-order", {
        detail: {
          ...options,
          returnTo:
            options.returnTo ??
            `${window.location.pathname}${window.location.search || ""}`,
        },
      }),
    );
  } catch {
    /* ignore */
  }
}

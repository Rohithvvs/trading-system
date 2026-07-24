import type { RecommendationPrefillRequest } from "../types";

/** Navigation state for the dedicated `/paper-order` page. */
export type PaperOrderNavState = {
  symbol?: string;
  side?: "BUY" | "SELL";
  prefill?: RecommendationPrefillRequest | null;
  orderId?: number | null;
  /** Where BUY originated — used by Back when history is shallow */
  returnTo?: string;
  currentPrice?: number | null;
  signal?: string | null;
  score?: number | null;
  confidence?: number | null;
  riskReward?: number | null;
};

export function isPaperOrderNavState(value: unknown): value is PaperOrderNavState {
  return Boolean(value) && typeof value === "object";
}

/**
 * Research data prefetcher.
 *
 * Preloads symbol detail data into cache when user hovers/focuses on a stock card.
 * Uses the custom appCache layer so subsequent navigation renders instantly.
 */
import { cachedFetch, CACHE_KEYS, getCached } from "./appCache";
import { fetchSymbolDetail } from "../api";

const PREFETCH_QUEUE = new Set<string>();
const PREFETCHED = new Set<string>();
let PREFETCH_TIMER: ReturnType<typeof setTimeout> | null = null;

const RESEARCH_CACHE_KEY = (symbol: string) => `research_detail:${symbol}`;

export function prefetchResearch(symbol: string): void {
  if (PREFETCHED.has(symbol)) return;
  PREFETCH_QUEUE.add(symbol);

  if (PREFETCH_TIMER) clearTimeout(PREFETCH_TIMER);
  PREFETCH_TIMER = setTimeout(() => {
    const batch = Array.from(PREFETCH_QUEUE);
    PREFETCH_QUEUE.clear();
    for (const sym of batch) {
      if (PREFETCHED.has(sym)) continue;
      PREFETCHED.add(sym);
      cachedFetch(
        RESEARCH_CACHE_KEY(sym),
        () => fetchSymbolDetail(sym),
        { swr: true, ttlMs: 10 * 60 * 1000, softTimeoutMs: 5000 },
      ).catch(() => {
        PREFETCHED.delete(sym);
      });
    }
  }, 200);
}

export function getCachedResearch(symbol: string): any | null {
  try {
    return getCached(RESEARCH_CACHE_KEY(symbol));
  } catch {
    return null;
  }
}

export function clearPrefetched(): void {
  PREFETCHED.clear();
}

export function markPrefetched(symbol: string): void {
  PREFETCHED.add(symbol);
}

export function isPrefetched(symbol: string): boolean {
  return PREFETCHED.has(symbol);
}

/**
 * Background prefetch after login so tabs open near-instantly.
 * Staggered + idle so dashboard first paint is not starved.
 */

import {
  authMe,
  fetchAnalytics,
  fetchApiHealth,
  fetchMarketOverview,
  fetchPaperAccountSummary,
  fetchPaperTradingDashboard,
  fetchAlerts,
  getTokenStatus,
  loadLatestScan,
  fetchUniverses,
} from "../api";
import { cachedFetch, CACHE_KEYS, invalidateCache } from "./appCache";
import { startKeepAlive } from "./keepAlive";

let prefetched = false;

export function prefetchAppData(): void {
  if (prefetched) return;
  prefetched = true;

  startKeepAlive();

  const runPriority = () => {
    // Priority 1: auth + token + market (cheap, needed everywhere)
    void Promise.all([
      cachedFetch(CACHE_KEYS.authMe, () => authMe(), { swr: true }).catch(() => null),
      cachedFetch(CACHE_KEYS.fyersToken, () => getTokenStatus(), { swr: true }).catch(() => null),
    ]);
  };

  const runPaperBundle = () => {
    void Promise.all([
      cachedFetch(CACHE_KEYS.paperDashboard, () => fetchPaperTradingDashboard(), { swr: true }).catch(() => null),
      cachedFetch(CACHE_KEYS.paperAccount, () => fetchPaperAccountSummary(), { swr: true }).catch(() => null),
      cachedFetch(CACHE_KEYS.paperAnalytics, () => fetchAnalytics(), { swr: true }).catch(() => null),
      cachedFetch(CACHE_KEYS.paperAlerts, () => fetchAlerts(), { swr: true }).catch(() => null),
    ]);
  };

  const runWorkstation = () => {
    void Promise.all([
      cachedFetch(CACHE_KEYS.latestScan, () => loadLatestScan(), { swr: true }).catch(() => null),
      cachedFetch(CACHE_KEYS.marketOverview, () => fetchMarketOverview(), { swr: true }).catch(() => null),
      cachedFetch(CACHE_KEYS.apiHealth, () => fetchApiHealth(), { swr: true }).catch(() => null),
      cachedFetch(CACHE_KEYS.universes, () => fetchUniverses(), { swr: true, ttlMs: 30 * 60 * 1000 }).catch(
        () => null,
      ),
    ]);
  };

  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(() => runPriority(), { timeout: 1500 });
    requestIdleCallback(() => runPaperBundle(), { timeout: 3500 });
    requestIdleCallback(() => runWorkstation(), { timeout: 6000 });
  } else {
    window.setTimeout(runPriority, 300);
    window.setTimeout(runPaperBundle, 900);
    window.setTimeout(runWorkstation, 1600);
  }
}

export function resetPrefetchFlag(): void {
  prefetched = false;
}

export function clearAllAppCaches(): void {
  invalidateCache();
  resetPrefetchFlag();
  // Clear legacy profile cache keys if present
  try {
    const keys: string[] = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (k?.startsWith("profile_cache_v1_")) keys.push(k);
    }
    keys.forEach((k) => sessionStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}

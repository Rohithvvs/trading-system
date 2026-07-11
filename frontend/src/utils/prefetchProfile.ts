/**
 * Background prefetch for User Profile — call after app/auth is ready.
 * Warm cache so opening Profile feels instant.
 */
import { authMe, fetchAnalytics, fetchPaperTradingDashboard, getTokenStatus } from "../api";
import { cachedFetch, PROFILE_CACHE_KEYS } from "./profileDataCache";

let prefetched = false;

export function prefetchProfileData(): void {
  if (prefetched) return;
  prefetched = true;

  // Stagger slightly so dashboard paint isn't competing for bandwidth
  const run = () => {
    void cachedFetch(PROFILE_CACHE_KEYS.me, () => authMe()).catch(() => null);
    // Parallel paper bundle after a tick
    window.setTimeout(() => {
      void Promise.all([
        cachedFetch(PROFILE_CACHE_KEYS.dashboard, () => fetchPaperTradingDashboard()).catch(() => null),
        cachedFetch(PROFILE_CACHE_KEYS.analytics, () => fetchAnalytics()).catch(() => null),
        cachedFetch(PROFILE_CACHE_KEYS.token, () => getTokenStatus()).catch(() => null),
      ]);
    }, 400);
  };

  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(() => run(), { timeout: 2500 });
  } else {
    window.setTimeout(run, 800);
  }
}

export function resetProfilePrefetchFlag(): void {
  prefetched = false;
}

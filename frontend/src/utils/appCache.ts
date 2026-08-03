/**
 * Application-wide in-memory + sessionStorage cache with:
 * - TTL (default 8 minutes)
 * - In-flight request deduplication
 * - Stale-while-revalidate (serve stale immediately, refresh in background)
 * - Soft timeout: return stale/cached if network exceeds threshold
 */

const DEFAULT_TTL_MS = 8 * 60 * 1000;
const STORAGE_PREFIX = "app_cache_v1_";
const DEFAULT_SOFT_TIMEOUT_MS = 3000;

type Entry<T> = { value: T; expiresAt: number; savedAt: number };

const memory = new Map<string, Entry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

/** Multi-user isolation: every cache key is scoped to the authenticated user. */
let _userScope: string | null = null;

export function setCacheUserScope(userId: string | null | undefined): void {
  const next = userId ? String(userId) : null;
  if (_userScope && next && _userScope !== next) {
    // Different user logged in — drop previous user's in-memory entries
    memory.clear();
    inflight.clear();
  }
  _userScope = next;
}

export function getCacheUserScope(): string | null {
  return _userScope;
}

/** Scope a logical key to the current user (paper_account:user_id pattern). */
export function scopedKey(key: string): string {
  if (!_userScope) return key;
  return `${key}:u:${_userScope}`;
}

function now() {
  return Date.now();
}

function storageKey(key: string) {
  return `${STORAGE_PREFIX}${scopedKey(key)}`;
}

export function getCached<T>(key: string, allowStale = false): T | null {
  const sk = scopedKey(key);
  const mem = memory.get(sk) as Entry<T> | undefined;
  if (mem) {
    if (mem.expiresAt > now() || allowStale) return mem.value;
    if (!allowStale) memory.delete(sk);
  }

  try {
    const raw = sessionStorage.getItem(storageKey(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Entry<T>;
    if (!parsed || typeof parsed.expiresAt !== "number") {
      sessionStorage.removeItem(storageKey(key));
      return null;
    }
    if (parsed.expiresAt <= now() && !allowStale) {
      // Keep stale in memory for SWR, but report miss unless allowStale
      memory.set(sk, parsed);
      return null;
    }
    memory.set(sk, parsed);
    return parsed.value;
  } catch {
    return null;
  }
}

/** Returns cached value even if expired (for SWR / timeout fallback). */
export function getStaleCached<T>(key: string): T | null {
  const sk = scopedKey(key);
  const mem = memory.get(sk) as Entry<T> | undefined;
  if (mem) return mem.value;
  try {
    const raw = sessionStorage.getItem(storageKey(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Entry<T>;
    if (!parsed) return null;
    memory.set(sk, parsed);
    return parsed.value;
  } catch {
    return null;
  }
}

export function setCached<T>(key: string, value: T, ttlMs = DEFAULT_TTL_MS): void {
  const sk = scopedKey(key);
  const entry: Entry<T> = { value, expiresAt: now() + ttlMs, savedAt: now() };
  memory.set(sk, entry);
  try {
    sessionStorage.setItem(storageKey(key), JSON.stringify(entry));
  } catch {
    // quota / private mode — memory still works
  }
}

export function invalidateCache(prefix?: string): void {
  if (!prefix) {
    memory.clear();
    inflight.clear();
    try {
      const keys: string[] = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        if (k?.startsWith(STORAGE_PREFIX)) keys.push(k);
      }
      keys.forEach((k) => sessionStorage.removeItem(k));
    } catch {
      /* ignore */
    }
    return;
  }
  for (const k of [...memory.keys()]) {
    if (k.startsWith(prefix)) memory.delete(k);
  }
  for (const k of [...inflight.keys()]) {
    if (k.startsWith(prefix)) inflight.delete(k);
  }
  try {
    const keys: string[] = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (k?.startsWith(STORAGE_PREFIX) && k.includes(prefix)) keys.push(k);
    }
    keys.forEach((k) => sessionStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new Error(`SOFT_TIMEOUT_${ms}`));
    }, ms);
    promise.then(
      (v) => {
        window.clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        window.clearTimeout(timer);
        reject(e);
      },
    );
  });
}

export type CachedFetchOptions = {
  force?: boolean;
  ttlMs?: number;
  /** If true, return stale cache immediately and revalidate in background. */
  swr?: boolean;
  /** Soft network timeout (ms). On timeout, return stale if available. Default 3000. */
  softTimeoutMs?: number;
};

/**
 * Deduped cached fetch. Multiple callers share one in-flight request.
 * With swr=true: returns fresh or stale immediately, refreshes in background.
 * With soft timeout: if network is slow, serves stale cache rather than blocking UI.
 */
export async function cachedFetch<T>(
  key: string,
  fetcher: () => Promise<T>,
  opts?: CachedFetchOptions,
): Promise<T> {
  const ttlMs = opts?.ttlMs ?? DEFAULT_TTL_MS;
  const softTimeoutMs = opts?.softTimeoutMs ?? DEFAULT_SOFT_TIMEOUT_MS;
  const sk = scopedKey(key);

  if (!opts?.force) {
    const hit = getCached<T>(key);
    if (hit !== null) {
      if (opts?.swr) {
        // Background revalidate (deduped)
        void revalidateInBackground(key, fetcher, ttlMs);
      }
      return hit;
    }
  }

  // SWR: serve stale while loading
  if (opts?.swr && !opts?.force) {
    const stale = getStaleCached<T>(key);
    if (stale !== null) {
      void revalidateInBackground(key, fetcher, ttlMs);
      return stale;
    }
  }

  const existing = inflight.get(sk) as Promise<T> | undefined;
  if (existing) return existing;

  const promise = (async () => {
    try {
      let value: T;
      try {
        value = await withTimeout(fetcher(), softTimeoutMs);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        // On force refresh (e.g. latest scan after F5), never substitute an older
        // cached scan — wait for the network result instead.
        const allowStaleFallback = !opts?.force;
        if (
          allowStaleFallback &&
          (msg.startsWith("SOFT_TIMEOUT_") || msg.includes("Failed to fetch") || msg.includes("Network"))
        ) {
          const stale = getStaleCached<T>(key);
          if (stale !== null) {
            console.info(`[cache] soft-timeout/network fallback for ${sk}`);
            // Keep revalidating in background without timeout wall
            void revalidateInBackground(key, fetcher, ttlMs, true);
            return stale;
          }
        }
        // No stale — fall through to full wait (or rethrow)
        if (msg.startsWith("SOFT_TIMEOUT_")) {
          value = await fetcher();
        } else {
          throw err;
        }
      }
      setCached(key, value, ttlMs);
      return value;
    } finally {
      inflight.delete(sk);
    }
  })();

  inflight.set(sk, promise);
  return promise;
}

function revalidateInBackground<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttlMs: number,
  force = false,
): void {
  const sk = scopedKey(key);
  if (!force && inflight.has(sk)) return;
  if (inflight.has(sk)) return;

  const promise = (async () => {
    try {
      const value = await fetcher();
      setCached(key, value, ttlMs);
      return value;
    } catch {
      return getStaleCached<T>(key) as T;
    } finally {
      inflight.delete(sk);
    }
  })();

  inflight.set(sk, promise);
}

/**
 * Pre-warm the cache with known values. Useful for research prefetching
 * where we want to seed the cache before navigation.
 */
export function preheatCache<T>(key: string, value: T, ttlMs = DEFAULT_TTL_MS): void {
  setCached(key, value, ttlMs);
}

/** Stable cache keys for frequently accessed resources. */
export const CACHE_KEYS = {
  authMe: "auth_me",
  paperDashboard: "paper_dashboard",
  paperDashboardSymbol: (sym: string) => `paper_dashboard:${sym}`,
  paperAccount: "paper_account_summary",
  paperAnalytics: "paper_analytics",
  paperDailyAnalytics: (period: string) => `paper_daily_analytics:${period}`,
  paperDailyJournal: (date: string) => `paper_daily_journal:${date}`,
  paperAlerts: "paper_alerts",
  paperTrades: "paper_trades",
  paperPositions: "paper_positions",
  paperPendingOrders: "paper_pending_orders",
  paperTransactions: (page: number) => `paper_tx:${page}`,
  fyersToken: "fyers_token_status",
  fyersTokenHistory: "fyers_token_history",
  marketOverview: "market_overview",
  marketEngineStatus: "market_engine_status",
  marketEngineHealth: "market_engine_health",
  apiHealth: "api_health",
  latestScan: "latest_scan",
  universes: "universes",
  savedScans: "saved_scans",
  workstationAlerts: "workstation_alerts",
  riskSettings: "risk_settings",
  scanHistory: "scan_history",
} as const;

// Re-export profile-compatible names so profile code can migrate gradually
export const PROFILE_CACHE_KEYS = {
  me: CACHE_KEYS.authMe,
  dashboard: CACHE_KEYS.paperDashboard,
  analytics: CACHE_KEYS.paperAnalytics,
  token: CACHE_KEYS.fyersToken,
  health: CACHE_KEYS.apiHealth,
} as const;

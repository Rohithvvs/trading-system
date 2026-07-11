/**
 * In-memory + sessionStorage cache for User Profile data.
 * TTL 8 minutes — avoids repeated heavy paper/analytics calls while navigating.
 */

const TTL_MS = 8 * 60 * 1000;
const STORAGE_PREFIX = "profile_cache_v1_";

type Entry<T> = { value: T; expiresAt: number };

const memory = new Map<string, Entry<unknown>>();

function now() {
  return Date.now();
}

function storageKey(key: string) {
  return `${STORAGE_PREFIX}${key}`;
}

export function getCached<T>(key: string): T | null {
  const mem = memory.get(key) as Entry<T> | undefined;
  if (mem && mem.expiresAt > now()) return mem.value;
  if (mem) memory.delete(key);

  try {
    const raw = sessionStorage.getItem(storageKey(key));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Entry<T>;
    if (!parsed || typeof parsed.expiresAt !== "number" || parsed.expiresAt <= now()) {
      sessionStorage.removeItem(storageKey(key));
      return null;
    }
    memory.set(key, parsed);
    return parsed.value;
  } catch {
    return null;
  }
}

export function setCached<T>(key: string, value: T): void {
  const entry: Entry<T> = { value, expiresAt: now() + TTL_MS };
  memory.set(key, entry);
  try {
    sessionStorage.setItem(storageKey(key), JSON.stringify(entry));
  } catch {
    // quota / private mode — memory still works
  }
}

export function invalidateProfileCache(prefix?: string): void {
  if (!prefix) {
    memory.clear();
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
}

/** Dedupe in-flight fetches so parallel callers share one network request. */
const inflight = new Map<string, Promise<unknown>>();

export async function cachedFetch<T>(
  key: string,
  fetcher: () => Promise<T>,
  opts?: { force?: boolean },
): Promise<T> {
  if (!opts?.force) {
    const hit = getCached<T>(key);
    if (hit !== null) return hit;
  }
  const existing = inflight.get(key) as Promise<T> | undefined;
  if (existing) return existing;

  const promise = (async () => {
    try {
      const value = await fetcher();
      setCached(key, value);
      return value;
    } finally {
      inflight.delete(key);
    }
  })();

  inflight.set(key, promise);
  return promise;
}

export const PROFILE_CACHE_KEYS = {
  me: "auth_me",
  dashboard: "paper_dashboard",
  analytics: "paper_analytics",
  token: "fyers_token",
  health: "api_health",
} as const;

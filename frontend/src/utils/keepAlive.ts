/**
 * Lightweight keep-alive for Render free-tier cold starts.
 * Pings only /health every 10 minutes — never expensive endpoints.
 * Also warms the connection pool on the first successful response.
 */

import { apiUrl } from "../config";

const INTERVAL_MS = 10 * 60 * 1000;
let timerId: number | null = null;
let started = false;

async function pingHealth(): Promise<void> {
  const url = apiUrl("/health");
  const startedAt = performance.now();
  try {
    const res = await fetch(url, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const ms = Math.round(performance.now() - startedAt);
    console.info(`[keep-alive] /health -> ${res.status} (${ms}ms)`);
  } catch (err) {
    const ms = Math.round(performance.now() - startedAt);
    console.warn(`[keep-alive] /health failed (${ms}ms)`, err);
  }
}

/** Start background keep-alive (idempotent). Safe to call after login or app boot. */
export function startKeepAlive(): void {
  if (started || typeof window === "undefined") return;
  started = true;

  // Immediate warm-up after a short delay so first paint isn't competing
  const warm = () => {
    void pingHealth();
  };
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(() => warm(), { timeout: 4000 });
  } else {
    window.setTimeout(warm, 2000);
  }

  timerId = window.setInterval(() => void pingHealth(), INTERVAL_MS);
}

export function stopKeepAlive(): void {
  if (timerId != null) {
    window.clearInterval(timerId);
    timerId = null;
  }
  started = false;
}

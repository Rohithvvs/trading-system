/**
 * Central API configuration for the Trading System frontend.
 *
 * Production (Vercel): VITE_API_URL must be the HTTPS Render backend.
 *   VITE_API_URL=https://trading-system-2-rl0x.onrender.com
 *
 * There is NO localhost fallback in production builds.
 */

/** Hard safety net if env is missing/mis-set in a production bundle. */
export const PRODUCTION_API_URL = "https://trading-system-2-rl0x.onrender.com";

function normalizeBaseUrl(raw: string | undefined): string {
  if (!raw) return "";
  return raw.replace(/\/+$/, "");
}

function isLocalHostUrl(url: string): boolean {
  return /^(https?:\/\/)?(localhost|127\.0\.0\.1)(:\d+)?/i.test(url);
}

function resolveApiBaseUrl(): string {
  const fromEnv = normalizeBaseUrl(
    import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "",
  );

  // ---------- PRODUCTION ----------
  if (import.meta.env.PROD) {
    if (fromEnv && !isLocalHostUrl(fromEnv)) {
      if (fromEnv.startsWith("http://")) {
        // Mixed content will break mobile HTTPS pages — upgrade if possible.
        console.warn(
          `[config] VITE_API_URL is HTTP in production (${fromEnv}). Prefer HTTPS.`,
        );
      }
      return fromEnv;
    }

    if (fromEnv && isLocalHostUrl(fromEnv)) {
      console.error(
        `[config] Refusing localhost VITE_API_URL in production (${fromEnv}). ` +
          `Using ${PRODUCTION_API_URL}`,
      );
    } else {
      console.warn(
        `[config] VITE_API_URL missing in production. Using ${PRODUCTION_API_URL}`,
      );
    }
    // Never return localhost / empty loopback in production.
    return PRODUCTION_API_URL;
  }

  // ---------- DEVELOPMENT ----------
  if (fromEnv) {
    return fromEnv;
  }
  return "http://127.0.0.1:8000";
}

/** Backend origin with no trailing slash. */
export const API_BASE_URL = resolveApiBaseUrl();

/** Build an absolute API URL for a path starting with `/`. */
export function apiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

export function getWsBaseUrl(): string {
  if (API_BASE_URL) {
    return API_BASE_URL.replace(/^http/, "ws");
  }
  if (import.meta.env.PROD) {
    return PRODUCTION_API_URL.replace(/^http/, "ws");
  }
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}`;
  }
  return "ws://127.0.0.1:8000";
}

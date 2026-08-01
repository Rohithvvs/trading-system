/**
 * Admin Panel API client (Sprint 4).
 * Uses cookie session auth (credentials: include), same as the rest of the SPA.
 *
 * Hardening: default request timeout (H-1); request diagnostics (M-3).
 * Never logs tokens, cookies, or response bodies (NFR-003).
 */

import { apiUrl } from "./config";
import {
  ApiClientError,
  mapHttpError,
  mapNetworkError,
  toUserFacingApiMessage,
} from "./utils/apiErrors";

/** Default admin API timeout (ms) — audit H-1 */
export const ADMIN_FETCH_TIMEOUT_MS = 25_000;

/** Dev-only diagnostics (M-3). Matches main `api.ts` pattern; production is silent. */
const IS_DEV =
  (typeof import.meta !== "undefined" && Boolean((import.meta as { env?: { DEV?: boolean } }).env?.DEV)) ||
  (typeof window !== "undefined" && Boolean((window as { __VITE_DEV__?: boolean }).__VITE_DEV__));

function adminLog(...args: unknown[]) {
  if (IS_DEV) console.info(...args);
}

function adminWarn(...args: unknown[]) {
  if (IS_DEV) console.warn(...args);
}

/** Redact query values that might contain PII (search emails); keep keys for debugging. */
function safeAdminPath(path: string): string {
  try {
    const q = path.indexOf("?");
    if (q < 0) return path;
    const base = path.slice(0, q);
    const params = new URLSearchParams(path.slice(q + 1));
    if (params.has("search")) params.set("search", "[redacted]");
    const qs = params.toString();
    return qs ? `${base}?${qs}` : base;
  } catch {
    return path.split("?")[0] ?? path;
  }
}

export type AdminRole = "trader" | "admin";

export type AdminUser = {
  id: string;
  email: string;
  full_name: string;
  role: AdminRole;
  is_active: boolean;
  created_at: string;
};

export type AdminUserListResponse = {
  items: AdminUser[];
  total: number;
  page: number;
  size: number;
};

export type FeaturePermission = {
  id: string;
  feature_key: string;
  description: string;
  allowed_roles: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type FeatureListResponse = {
  items: FeaturePermission[];
};

export class AdminApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "AdminApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function parseDetail(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail
        .map((d: { msg?: string }) => d?.msg)
        .filter(Boolean)
        .join("; ");
    }
    if (data?.message) return String(data.message);
  } catch {
    /* ignore */
  }
  return response.statusText || `Request failed (${response.status})`;
}

async function adminFetch(path: string, init?: RequestInit, label = "Admin API"): Promise<Response> {
  const url = apiUrl(path);
  const safePath = safeAdminPath(path);
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };
  if (method !== "GET" && method !== "HEAD" && !headers["Content-Type"] && !headers["content-type"]) {
    headers["Content-Type"] = "application/json";
  }

  const externalSignal = init?.signal;
  const controller = new AbortController();
  // Prefer global timers (jsdom + browser); audit H-1 timeout protection
  const timeoutId = setTimeout(() => controller.abort(), ADMIN_FETCH_TIMEOUT_MS);
  const startedAt = typeof performance !== "undefined" ? performance.now() : Date.now();

  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort();
    else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }

  adminLog(`[admin-api] ${label} -> ${method} ${safePath}`);

  try {
    const response = await fetch(url, {
      ...init,
      credentials: "include",
      headers,
      signal: controller.signal,
    });
    const elapsedMs = Math.round(
      (typeof performance !== "undefined" ? performance.now() : Date.now()) - startedAt,
    );
    adminLog(`[admin-api] ${label} <- ${response.status} ${safePath} (${elapsedMs}ms)`);

    if ([502, 503, 504, 521, 522, 523, 524].includes(response.status)) {
      adminWarn(`[admin-api] ${label} gateway error ${response.status} ${safePath} (${elapsedMs}ms)`);
      throw mapHttpError(response.status, url);
    }
    return response;
  } catch (error) {
    const elapsedMs = Math.round(
      (typeof performance !== "undefined" ? performance.now() : Date.now()) - startedAt,
    );
    // Unmount/cancel is expected — avoid noise (still mapped for callers that need it)
    if (externalSignal?.aborted) {
      adminLog(`[admin-api] ${label} aborted ${safePath} (${elapsedMs}ms)`);
    } else if (error instanceof ApiClientError) {
      adminWarn(`[admin-api] ${label} client error ${safePath} (${elapsedMs}ms)`, error.code, error.message);
    } else {
      adminWarn(`[admin-api] ${label} network error ${safePath} (${elapsedMs}ms)`, error);
    }
    if (error instanceof ApiClientError) throw error;
    throw mapNetworkError(error, url, label);
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener("abort", onExternalAbort);
    }
  }
}

function logAdminHttpFailure(label: string, status: number, detail: string): void {
  adminWarn(`[admin-api] ${label} HTTP ${status}: ${detail}`);
}

export function adminErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (error instanceof AdminApiError) return error.detail || fallback;
  if (error instanceof ApiClientError) return error.message || fallback;
  return toUserFacingApiMessage(error, fallback);
}

export function isAuthzAdminError(error: unknown): boolean {
  return error instanceof AdminApiError && (error.status === 401 || error.status === 403);
}

export async function listAdminUsers(params?: {
  page?: number;
  size?: number;
  search?: string;
  signal?: AbortSignal;
}): Promise<AdminUserListResponse> {
  const page = params?.page ?? 1;
  const size = params?.size ?? 20;
  const qs = new URLSearchParams({ page: String(page), size: String(size) });
  const search = params?.search?.trim();
  if (search) qs.set("search", search);

  const response = await adminFetch(
    `/admin/users?${qs.toString()}`,
    { signal: params?.signal },
    "List admin users",
  );
  if (!response.ok) {
    const detail = await parseDetail(response);
    logAdminHttpFailure("List admin users", response.status, detail);
    throw new AdminApiError(response.status, detail);
  }
  return response.json();
}

export async function updateUserRole(userId: string, role: AdminRole): Promise<AdminUser> {
  const response = await adminFetch(
    `/admin/users/${encodeURIComponent(userId)}/role`,
    { method: "PATCH", body: JSON.stringify({ role }) },
    "Update user role",
  );
  if (!response.ok) {
    const detail = await parseDetail(response);
    logAdminHttpFailure("Update user role", response.status, detail);
    throw new AdminApiError(response.status, detail);
  }
  return response.json();
}

export async function listAdminFeatures(params?: {
  signal?: AbortSignal;
}): Promise<FeatureListResponse> {
  const response = await adminFetch(
    "/admin/features",
    { signal: params?.signal },
    "List admin features",
  );
  if (!response.ok) {
    const detail = await parseDetail(response);
    logAdminHttpFailure("List admin features", response.status, detail);
    throw new AdminApiError(response.status, detail);
  }
  return response.json();
}

/**
 * Sprint 5: authenticated feature catalog for any signed-in role.
 * Uses DB policy so admin edits apply to traders (AC-FEAT-05).
 */
export async function listSessionFeatures(params?: {
  signal?: AbortSignal;
}): Promise<FeatureListResponse> {
  const response = await adminFetch(
    "/features",
    { signal: params?.signal },
    "List session features",
  );
  if (!response.ok) {
    const detail = await parseDetail(response);
    logAdminHttpFailure("List session features", response.status, detail);
    throw new AdminApiError(response.status, detail);
  }
  return response.json();
}

export async function updateFeaturePermission(
  featureKey: string,
  body: { allowed_roles: string[] },
): Promise<FeaturePermission> {
  const response = await adminFetch(
    `/admin/features/${encodeURIComponent(featureKey)}`,
    { method: "PATCH", body: JSON.stringify({ allowed_roles: body.allowed_roles }) },
    "Update feature permission",
  );
  if (!response.ok) {
    const detail = await parseDetail(response);
    logAdminHttpFailure("Update feature permission", response.status, detail);
    throw new AdminApiError(response.status, detail);
  }
  return response.json();
}

export const CRITICAL_FEATURE_KEYS = new Set(["admin_panel", "user_management"]);

/**
 * Shared helpers for FYERS token status across UI surfaces.
 *
 * Dual status model (Sprint 4):
 * - UI manual save writes status "active" / "inactive"
 * - Automation writes "Success" / "Failed"
 * Prefer connection_status + access_token_active when present.
 */

export type TokenStatusLike = {
  status?: string | null;
  connection_status?: string | null;
  access_token_active?: boolean | null;
  expires_in_seconds?: number | null;
  valid?: boolean | null;
  last_error?: string | null;
};

export function isFyersTokenUsable(token: TokenStatusLike | null | undefined): boolean {
  if (!token) return false;
  if (token.valid === true) return true;
  if (token.access_token_active === true) return true;
  const conn = String(token.connection_status || "").toLowerCase();
  if (conn === "connected" || conn === "expiring soon") return true;
  const st = String(token.status || "").toLowerCase();
  if (st === "active" || st === "success") return true;
  // Failed automation may still leave a usable prior token
  if (st === "failed" && token.access_token_active === true) return true;
  return false;
}

export function isFyersTokenExpired(token: TokenStatusLike | null | undefined): boolean {
  if (!token) return false;
  const conn = String(token.connection_status || "").toLowerCase();
  if (conn === "expired") return true;
  if (token.expires_in_seconds != null && Number(token.expires_in_seconds) <= 0) {
    return true;
  }
  return false;
}

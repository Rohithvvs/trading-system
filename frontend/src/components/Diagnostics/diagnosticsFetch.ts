/**
 * Diagnostics API fetch helper.
 *
 * When VITE_API_KEY / VITE_DIAGNOSTICS_API_KEY is set, sends
 * Authorization: Bearer <key> to match backend verify_api_key.
 * Always includes credentials for cookie-based sessions.
 */

function diagnosticsAuthHeaders(): HeadersInit {
  const key =
    (import.meta.env.VITE_API_KEY as string | undefined) ||
    (import.meta.env.VITE_DIAGNOSTICS_API_KEY as string | undefined) ||
    "";
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (key) {
    headers.Authorization = `Bearer ${key}`;
  }
  return headers;
}

export async function diagnosticsFetch(
  url: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = {
    ...diagnosticsAuthHeaders(),
    ...(init.headers ?? {}),
  };
  return fetch(url, {
    ...init,
    credentials: "include",
    headers,
  });
}

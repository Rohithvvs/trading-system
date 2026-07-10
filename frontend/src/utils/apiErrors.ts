/**
 * Global API / network error mapping for user-facing messages.
 * Never surface raw browser strings like "Failed to fetch" to end users.
 */

export type ApiErrorCode =
  | "NETWORK_LOST"
  | "SERVER_UNREACHABLE"
  | "SERVER_UNAVAILABLE"
  | "TIMEOUT"
  | "CORS"
  | "MIXED_CONTENT"
  | "LOCALHOST_IN_PROD"
  | "BACKEND_URL_BAD"
  | "HTTP_ERROR"
  | "UNKNOWN";

export class ApiClientError extends Error {
  readonly code: ApiErrorCode;
  readonly url?: string;
  readonly status?: number;
  readonly cause?: unknown;

  constructor(
    message: string,
    options: {
      code: ApiErrorCode;
      url?: string;
      status?: number;
      cause?: unknown;
    },
  ) {
    super(message);
    this.name = "ApiClientError";
    this.code = options.code;
    this.url = options.url;
    this.status = options.status;
    this.cause = options.cause;
  }
}

function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const name = (error as { name?: string }).name;
  return name === "AbortError" || name === "TimeoutError";
}

function rawMessage(error: unknown): string {
  if (error instanceof Error) return error.message || "";
  return String(error ?? "");
}

function looksLikeCors(message: string): boolean {
  const m = message.toLowerCase();
  return (
    m.includes("cors") ||
    m.includes("cross-origin") ||
    m.includes("access-control-allow-origin") ||
    m.includes("blocked by cors policy")
  );
}

function looksLikeMixedContent(message: string, url?: string): boolean {
  const m = message.toLowerCase();
  if (m.includes("mixed content") || m.includes("insecure")) return true;
  if (typeof window !== "undefined" && window.location.protocol === "https:" && url?.startsWith("http://")) {
    return true;
  }
  return false;
}

function looksLikeLocalhostMisconfig(url?: string): boolean {
  if (!url) return false;
  if (typeof window === "undefined") return false;
  const pageIsRemote = !/^(localhost|127\.0\.0\.1)$/i.test(window.location.hostname);
  const apiIsLocal = /https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/i.test(url);
  return pageIsRemote && apiIsLocal;
}

function looksLikeOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

/**
 * Map a low-level fetch / TypeError into a stable user-facing ApiClientError.
 */
export function mapNetworkError(error: unknown, url?: string, label?: string): ApiClientError {
  const message = rawMessage(error);
  const prefix = label ? `${label}: ` : "";

  if (isAbortError(error) || /timed?\s*out|timeout/i.test(message)) {
    return new ApiClientError(`${prefix}Request timed out.`.trim(), {
      code: "TIMEOUT",
      url,
      cause: error,
    });
  }

  if (looksLikeOffline()) {
    return new ApiClientError(`${prefix}Network connection lost.`.trim(), {
      code: "NETWORK_LOST",
      url,
      cause: error,
    });
  }

  if (looksLikeLocalhostMisconfig(url)) {
    return new ApiClientError(
      `${prefix}Backend URL is unreachable. The app is calling localhost instead of the production server.`.trim(),
      {
        code: "LOCALHOST_IN_PROD",
        url,
        cause: error,
      },
    );
  }

  if (looksLikeMixedContent(message, url)) {
    return new ApiClientError(
      `${prefix}Backend URL is unreachable. The page is HTTPS but the API URL is insecure HTTP.`.trim(),
      {
        code: "MIXED_CONTENT",
        url,
        cause: error,
      },
    );
  }

  if (looksLikeCors(message)) {
    return new ApiClientError(`${prefix}CORS blocked request.`.trim(), {
      code: "CORS",
      url,
      cause: error,
    });
  }

  // Browser TypeError: Failed to fetch / Load failed / NetworkError
  if (
    /failed to fetch|load failed|networkerror|network request failed|err_connection|err_name_not_resolved|err_cert|err_ssl|err_failed/i.test(
      message,
    )
  ) {
    return new ApiClientError(`${prefix}Cannot connect to server.`.trim(), {
      code: "SERVER_UNREACHABLE",
      url,
      cause: error,
    });
  }

  if (/unreachable|refused|enotfound|econnrefused|econnreset/i.test(message)) {
    return new ApiClientError(`${prefix}Backend URL is unreachable.`.trim(), {
      code: "BACKEND_URL_BAD",
      url,
      cause: error,
    });
  }

  return new ApiClientError(`${prefix}Cannot connect to server.`.trim(), {
    code: "UNKNOWN",
    url,
    cause: error,
  });
}

/**
 * Map HTTP status codes that mean "server up but unavailable" into friendly text.
 */
export function mapHttpError(status: number, url?: string, detail?: string): ApiClientError {
  if (status === 0) {
    return new ApiClientError("Cannot connect to server.", { code: "SERVER_UNREACHABLE", url, status });
  }
  if (status === 408 || status === 504) {
    return new ApiClientError("Request timed out.", { code: "TIMEOUT", url, status });
  }
  if (status === 502 || status === 503 || status === 521 || status === 522 || status === 523 || status === 524) {
    return new ApiClientError("Server unavailable.", { code: "SERVER_UNAVAILABLE", url, status });
  }
  const fallback = detail?.trim() || `Request failed (HTTP ${status}).`;
  return new ApiClientError(fallback, { code: "HTTP_ERROR", url, status });
}

/**
 * Convert any thrown value into a clean UI string (never "Failed to fetch").
 */
export function toUserFacingApiMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (error instanceof ApiClientError) {
    return error.message;
  }
  const msg = rawMessage(error);
  if (!msg || /failed to fetch|load failed|networkerror/i.test(msg)) {
    return mapNetworkError(error).message;
  }
  // Strip noisy diagnostic prefixes from older client throws
  if (/failed before reaching backend/i.test(msg)) {
    return mapNetworkError(error).message;
  }
  return msg || fallback;
}

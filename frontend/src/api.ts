import type {
  AnalysisMode,
  FullAnalysisResponse,
  PaperOrder,
  PaperOrderActionResponse,
  PaperOrderTicketState,
  PaperPosition,
  PaperQuoteResponse,
  PaperTradingDashboardResponse,
  PaperTradeHistoryItem,
  RecommendationPrefillRequest,
  RecommendationPrefillResponse,
  ScreenerResponse,
  TimeframeConfig,
  SymbolDetail,
  MarketEngineStatus,
} from "./types";
import { apiUrl } from "./config";
import {
  ApiClientError,
  mapHttpError,
  mapNetworkError,
  toUserFacingApiMessage,
} from "./utils/apiErrors";
import { cachedFetch, CACHE_KEYS, invalidateCache, setCached } from "./utils/appCache";

export { toUserFacingApiMessage, ApiClientError } from "./utils/apiErrors";

const IS_DEV = typeof window !== "undefined" && (window as any).__VITE_DEV__;

function apiLog(...args: unknown[]) {
  if (IS_DEV) console.info(...args);
}

function apiWarn(...args: unknown[]) {
  if (IS_DEV) console.warn(...args);
}

async function fetchWithDiagnostics(
  path: string,
  init: RequestInit | undefined,
  label: string,
): Promise<Response> {
  const url = apiUrl(path);
  const startedAt = performance.now();
  apiLog(`[api] ${label} -> ${url}`);

  try {
    const method = (init?.method ?? "GET").toUpperCase();
    // Avoid Content-Type on GET/HEAD — it forces CORS preflight on every poll.
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
    };
    if (method !== "GET" && method !== "HEAD" && !headers["Content-Type"] && !headers["content-type"]) {
      headers["Content-Type"] = "application/json";
    }
    const fetchInit: RequestInit = {
      ...init,
      credentials: "include",
      headers,
    };
    const response = await fetch(url, fetchInit);
    const elapsedMs = Math.round(performance.now() - startedAt);
    apiLog(`[api] ${label} <- ${response.status} ${url} (${elapsedMs}ms)`);

    // Global handling for gateway / cold-start style failures
    if ([502, 503, 504, 521, 522, 523, 524].includes(response.status)) {
      throw mapHttpError(response.status, url);
    }
    return response;
  } catch (error) {
    const elapsedMs = Math.round(performance.now() - startedAt);
    if (error instanceof ApiClientError) {
      apiWarn(`[api] ${label} client error at ${url} (${elapsedMs}ms)`, error);
      throw error;
    }
    apiWarn(`[api] ${label} network error at ${url} (${elapsedMs}ms)`, error);
    throw mapNetworkError(error, url, label);
  }
}

/** Lightweight reachability probe used by auth screens and ops badges. */
export async function checkBackendHealth(): Promise<{
  ok: boolean;
  status: number | null;
  url: string;
  message: string;
  latencyMs: number;
}> {
  const url = apiUrl("/health");
  const startedAt = performance.now();
  try {
    const response = await fetch(url, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const latencyMs = Math.round(performance.now() - startedAt);
    if (!response.ok) {
      const err = mapHttpError(response.status, url);
      return { ok: false, status: response.status, url, message: err.message, latencyMs };
    }
    return {
      ok: true,
      status: response.status,
      url,
      message: "Server is reachable.",
      latencyMs,
    };
  } catch (error) {
    const latencyMs = Math.round(performance.now() - startedAt);
    const mapped = mapNetworkError(error, url);
    return {
      ok: false,
      status: null,
      url,
      message: mapped.message,
      latencyMs,
    };
  }
}

// `runFullAnalysis` removed — frontend uses `runPresetScreener` instead.

export interface ScannerProgressUpdate {
  stage: string;
  progress: number;
  current_symbol?: string;
  worker_id?: number;
  done?: number;
  remaining?: number;
  total_fetch?: number;
  total_scoring?: number;
  eta_sec?: number;
}

export async function runPresetScreener(
  mode: AnalysisMode,
  timeframe: TimeframeConfig,
  symbols: string[],
  topN: number,
  onProgress?: (update: ScannerProgressUpdate) => void,
  signal?: AbortSignal,
): Promise<ScreenerResponse> {
  console.info("[scanner] runPresetScreener called", {
    mode,
    timeframe,
    symbolCount: symbols.length,
    topN,
  });
  
  // Client-side connect timeout — never leave UI at "Connecting data feed..." forever.
  const CONNECT_TIMEOUT_MS = 30_000;
  const connectTimer = setTimeout(() => {
    /* resolved via race below */
  }, CONNECT_TIMEOUT_MS);

  let response: Response;
  try {
    const fetchPromise = fetchWithDiagnostics("/analysis/screener/full", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ mode, timeframe, symbols, top_n: topN }),
      signal,
    }, "Scanner request");

    const timeoutPromise = new Promise<never>((_, reject) => {
      const id = setTimeout(
        () => reject(new Error("Scanner connection timed out after 30s — check backend and broker token.")),
        CONNECT_TIMEOUT_MS,
      );
      if (signal) {
        signal.addEventListener("abort", () => clearTimeout(id), { once: true });
      }
    });
    response = await Promise.race([fetchPromise, timeoutPromise]);
  } finally {
    clearTimeout(connectTimer);
  }

  // Headers received — leave pure "Connecting..." state immediately.
  onProgress?.({
    stage: "Data feed connected — starting scan...",
    progress: 3,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to run screener");
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const body = await response.json();
    if (body?.status === "scan_in_progress") {
      throw Object.assign(
        new Error(body?.message || "SCAN_IN_PROGRESS"),
        { scanInProgress: true },
      );
    }
    throw new Error("Unexpected scanner response format");
  }

  if (!response.body) {
    throw new Error("No stream body available");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let payload: ScreenerResponse | null = null;
  // Server sends progress/heartbeat every ~5s. Stall if nothing for 90s.
  const STREAM_STALL_TIMEOUT_MS = 90_000;
  let lastProgressAt = Date.now();
  let sawRealProgress = false;

  while (true) {
    let result: ReadableStreamReadResult<Uint8Array>;
    try {
      const timeoutPromise = new Promise<never>((_, reject) => {
        const id = setTimeout(() => {
          const waited = Math.round((Date.now() - lastProgressAt) / 1000);
          reject(
            new Error(
              sawRealProgress
                ? `Scanner stream stalled — no progress for ${waited}s`
                : "Scanner stuck at startup — no progress events received. Check broker token and backend logs for [SCAN].",
            ),
          );
        }, STREAM_STALL_TIMEOUT_MS);
        if (signal) signal.addEventListener("abort", () => clearTimeout(id), { once: true });
      });
      result = await Promise.race([reader.read(), timeoutPromise]);
    } catch (err: any) {
      if (signal?.aborted) throw new Error("Scan cancelled");
      throw err;
    }
    if (result.done) break;

    lastProgressAt = Date.now();
    buffer += decoder.decode(result.value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const event of events) {
      if (!event.trim()) continue;

      // SSE comment keepalives reset stall timer (via lastProgressAt above).
      if (event.trim().startsWith(":")) {
        if (!sawRealProgress) {
          onProgress?.({
            stage: "Waiting for broker response...",
            progress: 5,
          });
        }
        continue;
      }

      const eventMatch = event.match(/event:\s*(.*?)\n/);
      const dataMatch = event.match(/data:\s*(.*)/);

      const eventType = eventMatch ? eventMatch[1].trim() : "message";
      const dataRaw = dataMatch ? dataMatch[1].trim() : null;

      if (!dataRaw) continue;

      try {
        const data = JSON.parse(dataRaw);

        if (eventType === "progress") {
          sawRealProgress = true;
          if (onProgress) {
            onProgress({
              stage: data.stage || "Scanning...",
              progress: typeof data.progress === "number" ? data.progress : 0,
              current_symbol: data.current_symbol,
              worker_id: data.worker_id,
              done: data.done,
              remaining: data.remaining,
              total_fetch: data.total_fetch,
              total_scoring: data.total_scoring,
              eta_sec: data.eta_sec,
            });
          }
        } else if (eventType === "result") {
          if (data.status === "error") {
            throw new Error(data.message || "Scanner encountered an internal error");
          } else if (data.status === "complete") {
            payload = data.result;
            onProgress?.({ stage: "Completed", progress: 100 });
          }
        }
      } catch (err) {
        if (err instanceof Error && err.message !== "Unexpected end of JSON input") {
          throw err;
        }
      }
    }
  }

  if (!payload) {
    throw new Error("Stream closed without sending a result");
  }

  console.info("[scanner] response summary", {
    scanned: payload.scanned_symbols,
    valid: payload.data_valid_symbols.length,
    eligible: payload.eligible_symbols.length,
    matched: payload.matched_symbols.length,
    shortlisted: payload.shortlisted_symbols.length,
    buy: payload.buy_candidate_symbols.length,
    watch: payload.watch_candidate_symbols.length,
    dataSource: payload.data_source,
    dataWarning: payload.data_warning,
    stoppedAt: payload.stopped_at_stage,
  });
  return payload;
}

async function _fetchPaperTradingDashboardRaw(selectedSymbol?: string): Promise<PaperTradingDashboardResponse> {
  const params = selectedSymbol ? `?selected_symbol=${encodeURIComponent(selectedSymbol)}` : "";
  const response = await fetchWithDiagnostics(`/paper-trading/dashboard${params}`, undefined, "Paper dashboard");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load paper trading dashboard");
  }
  return response.json() as Promise<PaperTradingDashboardResponse>;
}

export async function fetchPaperTradingDashboard(
  selectedSymbol?: string,
  opts?: { force?: boolean },
): Promise<PaperTradingDashboardResponse> {
  const key = selectedSymbol
    ? CACHE_KEYS.paperDashboardSymbol(selectedSymbol)
    : CACHE_KEYS.paperDashboard;
  return cachedFetch(key, () => _fetchPaperTradingDashboardRaw(selectedSymbol), {
    force: opts?.force,
    swr: !opts?.force,
    softTimeoutMs: 3000,
  });
}

export async function fetchPaperAccountSummary(opts?: { force?: boolean }): Promise<any> {
  return cachedFetch(
    CACHE_KEYS.paperAccount,
    async () => {
      const response = await fetchWithDiagnostics(`/paper-trading/account/summary`, undefined, "Paper account summary");
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to load account summary");
      }
      const payload = await response.json();
      // Single source of truth for Desk + Order capital. Log raw API shape for diagnostics.
      console.info("[paper-capital] api account_summary_response", {
        available_cash: payload?.available_cash ?? null,
        available_funds: payload?.available_funds ?? null,
        balance: payload?.balance ?? payload?.cash_balance ?? null,
        equity: payload?.equity ?? null,
        reserved_cash: payload?.reserved_cash ?? null,
        max_risk_per_trade: payload?.max_risk_per_trade ?? null,
        keys: payload && typeof payload === "object" ? Object.keys(payload) : [],
      });
      return payload;
    },
    { force: opts?.force, swr: !opts?.force, softTimeoutMs: 3000 },
  );
}

export async function fetchPaperQuote(symbol: string): Promise<PaperQuoteResponse> {
  const response = await fetchWithDiagnostics(
    `/paper-trading/symbols/${encodeURIComponent(symbol)}/quote`,
    undefined,
    "Paper quote",
  );
  if (!response.ok) {
    let detail: unknown = null;
    let message = "";
    try {
      detail = await response.json();
      if (detail && typeof detail === "object") {
        const d = detail as Record<string, unknown>;
        const nested = d.detail;
        if (nested && typeof nested === "object") {
          message = String((nested as Record<string, unknown>).reason ?? (nested as Record<string, unknown>).message ?? "");
        } else if (typeof nested === "string") {
          message = nested;
        } else {
          message = String(d.reason ?? d.message ?? "");
        }
      }
    } catch {
      try {
        message = await response.text();
      } catch {
        message = "";
      }
    }
    const err = new Error(message || "Failed to load live paper trading quote") as Error & {
      status?: number;
      detail?: unknown;
    };
    err.status = response.status;
    err.detail = detail;
    throw err;
  }
  return response.json() as Promise<PaperQuoteResponse>;
}

export async function resetPaperTradingAccount(startingBalance: number): Promise<PaperTradingDashboardResponse> {
  const response = await fetchWithDiagnostics("/paper-trading/account/reset", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ starting_balance: startingBalance }),
  }, "Paper account reset");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to reset account");
  }
  return response.json() as Promise<PaperTradingDashboardResponse>;
}

export async function placePaperOrder(ticket: PaperOrderTicketState, idempotencyKey?: string): Promise<PaperOrderActionResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "Idempotency-Key": idempotencyKey || crypto.randomUUID()
  };

  const response = await fetchWithDiagnostics("/paper-trading/orders", {
    method: "POST",
    headers,
    body: JSON.stringify({
      symbol: ticket.symbol,
      side: ticket.side,
      type: ticket.type,
      product_type: ticket.productType ?? "CNC",
      qty: ticket.qty,
      limit_price: ticket.limitPrice,
      stop_price: ticket.stopPrice,
      stop_loss: ticket.stopLoss,
      target: ticket.target,
      notes: ticket.notes,
      source_signal: ticket.sourceSignal,
      source_score: ticket.sourceScore,
      source_confidence: ticket.sourceConfidence,
    }),
  }, "Paper order");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to place paper order");
  }
  return response.json() as Promise<PaperOrderActionResponse>;
}

export async function startMarketEngine(): Promise<MarketEngineStatus> {
  const response = await fetchWithDiagnostics("/paper-trading/engine/start", { method: "POST" }, "Start market engine");
  if (!response.ok) throw new Error(await response.text() || "Failed to start market engine");
  return response.json() as Promise<MarketEngineStatus>;
}

export async function stopMarketEngine(): Promise<MarketEngineStatus> {
  const response = await fetchWithDiagnostics("/paper-trading/engine/stop", { method: "POST" }, "Stop market engine");
  if (!response.ok) throw new Error(await response.text() || "Failed to stop market engine");
  return response.json() as Promise<MarketEngineStatus>;
}

export async function fetchMarketEngineStatus(): Promise<MarketEngineStatus> {
  return cachedFetch(
    CACHE_KEYS.marketEngineStatus,
    async () => {
      const response = await fetchWithDiagnostics("/paper-trading/engine/status", undefined, "Market engine status");
      if (!response.ok) throw new Error(await response.text() || "Failed to load market engine status");
      return response.json() as Promise<MarketEngineStatus>;
    },
    { swr: true, ttlMs: 15 * 1000, softTimeoutMs: 2500 },
  );
}

export async function fetchPaperTradingEngineStatus(): Promise<import('./types').MarketEngineHealth> {
  return cachedFetch(
    CACHE_KEYS.marketEngineHealth,
    async () => {
      const response = await fetchWithDiagnostics("/paper-trading/engine-status", undefined, "Paper engine status");
      if (!response.ok) throw new Error(await response.text() || "Failed to load paper engine status");
      return response.json() as Promise<import('./types').MarketEngineHealth>;
    },
    { swr: true, ttlMs: 15 * 1000, softTimeoutMs: 2500 },
  );
}

export async function cancelPaperOrder(orderId: number): Promise<PaperOrderActionResponse> {
  const response = await fetchWithDiagnostics(`/paper-trading/orders/${orderId}/cancel`, {
    method: "POST",
  }, "Paper order cancel");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to cancel order");
  }
  return response.json() as Promise<PaperOrderActionResponse>;
}

export async function closePaperPosition(positionId: number): Promise<PaperOrderActionResponse> {
  const response = await fetchWithDiagnostics(`/paper-trading/positions/${positionId}/close`, {
    method: "POST",
  }, "Paper position close");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to close position");
  }
  return response.json() as Promise<PaperOrderActionResponse>;
}

export async function updatePaperPosition(position: Pick<PaperPosition, "id" | "stop_loss" | "target">): Promise<PaperOrderActionResponse> {
  const response = await fetchWithDiagnostics(`/paper-trading/positions/${position.id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      stop_loss: position.stop_loss,
      target: position.target,
    }),
  }, "Paper position update");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to update position");
  }
  return response.json() as Promise<PaperOrderActionResponse>;
}

export async function prefillPaperTrade(payload: RecommendationPrefillRequest): Promise<RecommendationPrefillResponse> {
  const response = await fetchWithDiagnostics("/paper-trading/from-recommendation", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }, "Paper prefill");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to prefill paper trade");
  }
  return response.json() as Promise<RecommendationPrefillResponse>;
}

export async function fetchSymbolDetail(symbol: string): Promise<SymbolDetail> {
  const response = await fetchWithDiagnostics(`/analysis/symbol/${encodeURIComponent(symbol)}/detail`, undefined, `Symbol detail ${symbol}`);
  if (!response.ok) {
    const raw = await response.text();
    let message = raw;
    try {
      const parsed = JSON.parse(raw);
      message = parsed?.detail?.message || parsed?.detail || parsed?.message || raw;
    } catch { /* use raw text */ }
    throw new Error(message || "Failed to fetch symbol detail");
  }
  const raw = await response.json();
  console.info("[api] symbol_detail raw response", { symbol, raw });
  return normalizeSymbolDetail(raw) as SymbolDetail;
}

function normalizeSymbolDetail(raw: any): any {
  if (!raw || typeof raw !== "object") return raw;
  const pick = (key: string, altKeys: string[]) => {
    if (raw[key] !== undefined) return raw[key];
    for (const alt of altKeys) {
      if (raw[alt] !== undefined) return raw[alt];
    }
    return undefined;
  };

  const year52_high = pick("year52_high", ["year52High", "year_52_high", "year_52_high"]);
  const year52_low = pick("year52_low", ["year52Low", "year_52_low", "year_52_low"]);
  const fiftyTwoWeekHigh = pick("52_week_high", ["fiftyTwoWeekHigh"]);
  const fiftyTwoWeekLow = pick("52_week_low", ["fiftyTwoWeekLow"]);

  const technical_extras = pick("technical_extras", ["technicalExtras"]) ?? null;
  if (technical_extras && typeof technical_extras === "object") {
    technical_extras.bollinger_status = technical_extras.bollinger_status ?? technical_extras.bollinger_position ?? null;
    technical_extras.bollinger_position = technical_extras.bollinger_position ?? technical_extras.bollinger_status ?? null;
  }
  const backtest_extras = pick("backtest_extras", ["backtestExtras"]) ?? null;
  const news_extras = pick("news_extras", ["newsExtras"]) ?? null;

  return {
    symbol: pick("symbol", ["Symbol"]) ?? raw.symbol,
    year52_high: year52_high ?? fiftyTwoWeekHigh ?? null,
    year52_low: year52_low ?? fiftyTwoWeekLow ?? null,
    company_name: pick("company_name", ["companyName", "short_name", "name"]) ?? null,
    company_description: pick("company_description", ["companyDescription", "description"]) ?? null,
    sector: pick("sector", ["Sector"]) ?? null,
    industry: pick("industry", ["Industry"]) ?? null,
    market_cap: pick("market_cap", ["marketCap", "marketCapCr", "market_capitalization"]) ?? null,
    technical_extras,
    backtest_extras,
    news_extras,
    ohlcv: pick("ohlcv", ["candles", "ohlc"]) ?? null,
    research: pick("research", ["Research", "swing_research"]) ?? null,
  };
}

export async function updatePaperOrder(orderId: number, payload: Partial<PaperOrderTicketState>): Promise<PaperOrderActionResponse> {
  const response = await fetchWithDiagnostics(`/paper-trading/orders/${orderId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }, "Paper order update");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to update paper order");
  }
  return response.json() as Promise<PaperOrderActionResponse>;
}

export async function deletePaperOrder(orderId: number): Promise<PaperOrderActionResponse> {
  const response = await fetchWithDiagnostics(`/paper-trading/orders/${orderId}`, {
    method: "DELETE",
  }, "Paper order delete");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to delete paper order");
  }
  return response.json() as Promise<PaperOrderActionResponse>;
}

export async function loadLatestScan(): Promise<ScreenerResponse | null> {
  return cachedFetch(
    CACHE_KEYS.latestScan,
    async () => {
      const response = await fetchWithDiagnostics("/analysis/scan/latest", undefined, "Load latest scan");
      if (!response.ok) {
        return null;
      }
      const data = await response.json() as ({ available?: boolean } & ScreenerResponse);
      if (!data.available) {
        return null;
      }
      return data as ScreenerResponse;
    },
    { swr: true, softTimeoutMs: 3000 },
  );
}

export async function getLatestScan(): Promise<any> {
  return cachedFetch(
    `${CACHE_KEYS.latestScan}:scanner`,
    async () => {
      const response = await fetchWithDiagnostics("/scanner/latest", {
        method: "GET",
        headers: {
          "Accept": "application/json",
        },
      }, "Get latest scan");

      if (!response.ok) {
        throw new Error("Failed to fetch latest scan");
      }

      return await response.json();
    },
    { swr: true, softTimeoutMs: 3000 },
  );
}


export async function loadTodayCandidates(): Promise<any[]> {
  const response = await fetchWithDiagnostics("/analysis/candidates/today", undefined, "Load today candidates");
  if (!response.ok) {
    return [];
  }
  return response.json() as Promise<any[]>;
}

export async function fetchAnalytics(opts?: { force?: boolean; period?: string }): Promise<any> {
  const period = opts?.period || "all";
  const cacheKey = `${CACHE_KEYS.paperAnalytics}:${period}`;
  return cachedFetch(
    cacheKey,
    async () => {
      const qs = new URLSearchParams({ period });
      const response = await fetchWithDiagnostics(
        `/paper-trading/analytics?${qs.toString()}`,
        undefined,
        "Paper analytics",
      );
      if (!response.ok) {
        const raw = await response.text();
        let message = raw;
        try {
          const parsed = JSON.parse(raw);
          message = parsed?.detail?.message || parsed?.detail || parsed?.message || raw;
        } catch { /* use raw text */ }
        throw new Error(typeof message === "string" ? message : "Failed to load analytics");
      }
      return response.json();
    },
    { force: opts?.force, swr: !opts?.force, softTimeoutMs: 8000, ttlMs: 2 * 60 * 1000 },
  );
}

export type DailyAnalyticsPeriod = "today" | "yesterday" | "week" | "month" | "custom";

export async function fetchDailyAnalytics(opts?: {
  period?: DailyAnalyticsPeriod;
  start_date?: string;
  end_date?: string;
  include_ai?: boolean;
  force?: boolean;
}): Promise<any> {
  const period = opts?.period ?? "today";
  const params = new URLSearchParams({ period, include_ai: String(opts?.include_ai ?? true) });
  if (opts?.start_date) params.set("start_date", opts.start_date);
  if (opts?.end_date) params.set("end_date", opts.end_date);
  const cacheKey = CACHE_KEYS.paperDailyAnalytics(
    `${period}:${opts?.start_date || ""}:${opts?.end_date || ""}`,
  );
  return cachedFetch(
    cacheKey,
    async () => {
      const response = await fetchWithDiagnostics(
        `/paper-trading/daily-analytics?${params.toString()}`,
        undefined,
        "Daily analytics",
      );
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to load daily analytics");
      }
      return response.json();
    },
    { force: opts?.force, swr: !opts?.force, softTimeoutMs: 3500, ttlMs: 3 * 60 * 1000 },
  );
}

export async function fetchDailyJournal(journalDate?: string): Promise<any> {
  const q = journalDate ? `?journal_date=${encodeURIComponent(journalDate)}` : "";
  return cachedFetch(
    CACHE_KEYS.paperDailyJournal(journalDate || "today"),
    async () => {
      const response = await fetchWithDiagnostics(`/paper-trading/daily-journal${q}`, undefined, "Daily journal");
      if (!response.ok) throw new Error(await response.text() || "Failed to load journal");
      return response.json();
    },
    { swr: true, ttlMs: 2 * 60 * 1000 },
  );
}

export async function saveDailyJournal(payload: {
  journal_date?: string;
  observations?: string;
  mistakes?: string;
  lessons?: string;
  tomorrow_plan?: string;
}): Promise<any> {
  const response = await fetchWithDiagnostics(
    `/paper-trading/daily-journal`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Save daily journal",
  );
  if (!response.ok) throw new Error(await response.text() || "Failed to save journal");
  const data = await response.json();
  // Bust journal + daily analytics cache for this user scope
  invalidateCache("paper_daily_journal");
  invalidateCache("paper_daily_analytics");
  return data;
}

export async function updatePaperAccountCapital(amount: number): Promise<any> {
  const response = await fetchWithDiagnostics(`/paper-trading/account/capital`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount }),
  }, "Update account capital");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to update account capital");
  }
  return response.json();
}

export async function fetchPaperAccountTransactions(page = 1, per_page = 20): Promise<any> {
  const params = `?page=${page}&per_page=${per_page}`;
  const response = await fetchWithDiagnostics(`/paper-trading/account/transactions${params}`, undefined, "Fetch account transactions");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to fetch transactions");
  }
  return response.json();
}

export async function fetchPositions(): Promise<PaperPosition[]> {
  const response = await fetchWithDiagnostics(`/paper-trading/positions`, undefined, "Paper positions");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load positions");
  }
  return response.json() as Promise<PaperPosition[]>;
}

export async function fetchPendingPaperOrders(): Promise<PaperOrder[]> {
  const response = await fetchWithDiagnostics(`/paper-trading/orders/pending`, undefined, "Paper pending orders");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load pending orders");
  }
  return response.json() as Promise<PaperOrder[]>;
}

export async function fetchPaperOrderHistory(): Promise<PaperOrder[]> {
  const response = await fetchWithDiagnostics(`/paper-trading/orders/history`, undefined, "Paper order history");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load order history");
  }
  return response.json() as Promise<PaperOrder[]>;
}

export async function fetchPaperTrades(): Promise<PaperTradeHistoryItem[]> {
  const response = await fetchWithDiagnostics(`/paper-trading/trades`, undefined, "Paper trade history");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load trade history");
  }
  return response.json() as Promise<PaperTradeHistoryItem[]>;
}

export async function squareOffAllPositions(): Promise<PaperTradingDashboardResponse> {
  const response = await fetchWithDiagnostics(`/paper-trading/positions/squareoff-all`, {
    method: "POST",
  }, "Square off all positions");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to square off all positions");
  }
  return response.json() as Promise<PaperTradingDashboardResponse>;
}

export async function fetchUnreadNotifications(): Promise<{ id: number; message: string; level: string; is_read: boolean; created_at: string }[]> {
  const response = await fetchWithDiagnostics(`/paper-trading/notifications/unread`, undefined, "Fetch unread notifications");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to fetch notifications");
  }
  return response.json();
}

export async function markNotificationsRead(ids: number[]): Promise<{ marked: number }> {
  const response = await fetchWithDiagnostics(`/paper-trading/notifications/mark-read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  }, "Mark notifications read");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to mark notifications read");
  }
  return response.json();
}

export async function fetchNotifications(unread: boolean | null = null, limit = 10): Promise<any[]> {
  const params = [] as string[];
  if (unread !== null) params.push(`unread=${unread}`);
  if (limit) params.push(`limit=${limit}`);
  const q = params.length ? `?${params.join("&")}` : "";
  const response = await fetchWithDiagnostics(`/paper-trading/notifications${q}`, undefined, "Fetch notifications");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to fetch notifications");
  }
  return response.json();
}

export async function markAllNotificationsRead(): Promise<{ marked: number }> {
  const response = await fetchWithDiagnostics(`/paper-trading/notifications/read-all`, {
    method: "POST",
  }, "Mark all notifications read");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to mark all notifications read");
  }
  return response.json();
}

export async function fetchAlerts(opts?: { force?: boolean }): Promise<{ id: number; symbol: string; condition: string; target_price: number; status: string; created_at: string; triggered_at?: string | null; triggered_price?: number | null }[]> {
  return cachedFetch(
    CACHE_KEYS.paperAlerts,
    async () => {
      const response = await fetchWithDiagnostics(`/paper-trading/alerts`, undefined, "Fetch alerts");
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Failed to fetch alerts");
      }
      return response.json();
    },
    { force: opts?.force, swr: !opts?.force },
  );
}

export async function createAlert(payload: { symbol: string; condition: string; price: number }) {
  const response = await fetchWithDiagnostics(`/paper-trading/alerts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, "Create alert");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to create alert");
  }
  return response.json();
}

export async function deleteAlert(alertId: number) {
  const response = await fetchWithDiagnostics(`/paper-trading/alerts/${alertId}`, {
    method: "DELETE",
  }, "Delete alert");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to delete alert");
  }
  return response.json();
}

export async function saveAccessToken(access_token: string) {
  const body = { access_token };
  const response = await fetchWithDiagnostics('/settings/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, 'Validate and save access token');
  
  if (!response.ok) {
    let errorMessage = 'Failed to validate access token';
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      errorMessage = await response.text() || errorMessage;
    }
    throw new Error(typeof errorMessage === "string" ? errorMessage : "Failed to validate access token");
  }
  // Force refresh of token caches after manual reconnect
  invalidateCache(CACHE_KEYS.fyersToken);
  invalidateCache(CACHE_KEYS.fyersTokenHistory);
  return response.json();
}

export type BrokerTokenPayload = {
  broker: string;
  access_token: string;
  api_key?: string;
  api_secret?: string;
  token_expiry?: string | null;
  notes?: string;
  validate?: boolean;
};

export async function fetchBrokerToken(broker = "FYERS") {
  const response = await fetchWithDiagnostics(
    `/api/broker-tokens?broker=${encodeURIComponent(broker)}`,
    undefined,
    "Broker token",
  );
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load broker token");
  }
  return response.json();
}

export async function saveBrokerToken(payload: BrokerTokenPayload) {
  // Never console.log payload.access_token / api_secret
  const response = await fetchWithDiagnostics(
    `/api/broker-tokens`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Save broker token",
  );
  if (!response.ok) {
    let errorMessage = "Failed to save broker token";
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      errorMessage = (await response.text()) || errorMessage;
    }
    throw new Error(typeof errorMessage === "string" ? errorMessage : "Failed to save broker token");
  }
  invalidateCache(CACHE_KEYS.fyersToken);
  invalidateCache(CACHE_KEYS.fyersTokenHistory);
  return response.json();
}

export async function updateBrokerToken(payload: Partial<BrokerTokenPayload> & { broker?: string }) {
  const response = await fetchWithDiagnostics(
    `/api/broker-tokens`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Update broker token",
  );
  if (!response.ok) {
    let errorMessage = "Failed to update broker token";
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      errorMessage = (await response.text()) || errorMessage;
    }
    throw new Error(typeof errorMessage === "string" ? errorMessage : "Failed to update broker token");
  }
  invalidateCache(CACHE_KEYS.fyersToken);
  invalidateCache(CACHE_KEYS.fyersTokenHistory);
  return response.json();
}

export async function deleteBrokerToken(broker = "FYERS") {
  const response = await fetchWithDiagnostics(
    `/api/broker-tokens?broker=${encodeURIComponent(broker)}`,
    { method: "DELETE" },
    "Delete broker token",
  );
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to delete broker token");
  }
  invalidateCache(CACHE_KEYS.fyersToken);
  invalidateCache(CACHE_KEYS.fyersTokenHistory);
  return response.json();
}

export async function validateBrokerToken(broker = "FYERS") {
  const response = await fetchWithDiagnostics(
    `/api/broker-tokens/validate?broker=${encodeURIComponent(broker)}`,
    { method: "POST" },
    "Validate broker token",
  );
  if (!response.ok) {
    let errorMessage = "Token validation failed";
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      errorMessage = (await response.text()) || errorMessage;
    }
    throw new Error(typeof errorMessage === "string" ? errorMessage : "Token validation failed");
  }
  invalidateCache(CACHE_KEYS.fyersToken);
  return response.json();
}

export async function testBrokerConnection(payload?: BrokerTokenPayload) {
  const response = await fetchWithDiagnostics(
    `/api/broker-tokens/test-connection`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        payload || { broker: "FYERS", access_token: "", validate: true },
      ),
    },
    "Test broker connection",
  );
  if (!response.ok) {
    let errorMessage = "Connection test failed";
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
    } catch {
      errorMessage = (await response.text()) || errorMessage;
    }
    throw new Error(typeof errorMessage === "string" ? errorMessage : "Connection test failed");
  }
  return response.json();
}

export async function getTokenStatus(opts?: { force?: boolean }) {
  return cachedFetch(
    CACHE_KEYS.fyersToken,
    async () => {
      const response = await fetchWithDiagnostics('/api/token/status', undefined, 'Token status');
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || 'Failed to get token status');
      }
      return response.json();
    },
    // Token status is DB-only on backend (no FYERS call) — cache 8 min; force on reconnect
    { force: opts?.force, swr: !opts?.force, ttlMs: 8 * 60 * 1000, softTimeoutMs: 3000 },
  );
}
export async function getTokenHistory(limit = 50) {
  return cachedFetch(
    CACHE_KEYS.fyersTokenHistory,
    async () => {
      const response = await fetchWithDiagnostics(`/api/token/history?limit=${encodeURIComponent(String(limit))}`, undefined, 'Token history');
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || 'Failed to get token history');
      }
      return response.json();
    },
    { swr: true, ttlMs: 8 * 60 * 1000 },
  );
}

export async function getFyersAuthUrl(): Promise<{ oauth_available: boolean; auth_url: string | null; callback_url: string | null; message?: string }> {
  const response = await fetchWithDiagnostics('/fyers/auth/url', undefined, 'FYERS auth URL');
  if (!response.ok) {
    const raw = await response.text();
    let message = raw;
    try {
      const parsed = JSON.parse(raw);
      message = parsed?.detail || parsed?.message || raw;
    } catch { /* use raw text */ }
    throw new Error(message || 'Failed to get FYERS auth URL');
  }
  return response.json();
}

export async function exchangeFyersAuthCode(authCode: string): Promise<{ status: string; message: string; expires_at?: string }> {
  const response = await fetchWithDiagnostics('/fyers/auth/exchange', {
    method: 'POST',
    body: JSON.stringify({ auth_code: authCode }),
  }, 'FYERS auth exchange');
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || 'Failed to exchange FYERS auth code');
  }
  return response.json();
}

export async function fetchUniverses(): Promise<{ name: string; symbols: string[]; count: number }[]> {
  return cachedFetch(
    CACHE_KEYS.universes,
    async () => {
      const response = await fetchWithDiagnostics("/workstation/universes", undefined, "Universes");
      if (!response.ok) throw new Error(await response.text() || "Failed to load universes");
      return response.json();
    },
    { swr: true, ttlMs: 30 * 60 * 1000 },
  );
}

export async function fetchBatchLight(symbols: string[]): Promise<{ symbols: { symbol: string; ltp: number | null; change_pct: number | null; company_name: string | null }[] }> {
  const response = await fetchWithDiagnostics("/analysis/symbol/batch-light", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols }),
  }, "Batch light");
  if (!response.ok) return { symbols: [] };
  return response.json();
}

export async function fetchMarketOverview(): Promise<any> {
  return cachedFetch(
    CACHE_KEYS.marketOverview,
    async () => {
      const response = await fetchWithDiagnostics("/workstation/market-overview", undefined, "Market overview");
      if (!response.ok) throw new Error(await response.text() || "Failed to load market overview");
      return response.json();
    },
    { swr: true, ttlMs: 2 * 60 * 1000, softTimeoutMs: 3000 },
  );
}

export async function fetchSavedScans(): Promise<any[]> {
  return cachedFetch(
    CACHE_KEYS.savedScans,
    async () => {
      const response = await fetchWithDiagnostics("/workstation/saved-scans", undefined, "Saved scans");
      if (!response.ok) throw new Error(await response.text() || "Failed to load saved scans");
      return response.json();
    },
    { swr: true },
  );
}

export async function saveScannerPreset(payload: any): Promise<any> {
  const response = await fetchWithDiagnostics("/workstation/saved-scans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, "Save scan");
  if (!response.ok) throw new Error(await response.text() || "Failed to save scan");
  return response.json();
}

export async function deleteScannerPreset(scanId: number): Promise<any> {
  const response = await fetchWithDiagnostics(`/workstation/saved-scans/${scanId}`, { method: "DELETE" }, "Delete scan");
  if (!response.ok) throw new Error(await response.text() || "Failed to delete scan");
  return response.json();
}

export async function fetchScanHistory(limit = 20): Promise<any[]> {
  const response = await fetchWithDiagnostics(`/workstation/scan-history?limit=${limit}`, undefined, "Scan history");
  if (!response.ok) throw new Error(await response.text() || "Failed to load scan history");
  return response.json();
}

export async function compareScan(scanId: number): Promise<any> {
  const response = await fetchWithDiagnostics(`/workstation/scan-history/${scanId}/compare`, undefined, "Compare scan");
  if (!response.ok) throw new Error(await response.text() || "Failed to compare scan");
  return response.json();
}

export async function fetchWorkstationAlerts(): Promise<any[]> {
  return cachedFetch(
    CACHE_KEYS.workstationAlerts,
    async () => {
      const response = await fetchWithDiagnostics("/workstation/alerts", undefined, "Workstation alerts");
      if (!response.ok) throw new Error(await response.text() || "Failed to load alerts");
      return response.json();
    },
    { swr: true },
  );
}

export async function createWorkstationAlert(payload: any): Promise<any> {
  const response = await fetchWithDiagnostics("/workstation/alerts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, "Create workstation alert");
  if (!response.ok) throw new Error(await response.text() || "Failed to create alert");
  return response.json();
}

export async function deleteWorkstationAlert(alertId: number): Promise<any> {
  const response = await fetchWithDiagnostics(`/workstation/alerts/${alertId}`, { method: "DELETE" }, "Delete workstation alert");
  if (!response.ok) throw new Error(await response.text() || "Failed to delete alert");
  return response.json();
}

export async function fetchRiskSettings(): Promise<any> {
  return cachedFetch(
    CACHE_KEYS.riskSettings,
    async () => {
      const response = await fetchWithDiagnostics("/workstation/risk-settings", undefined, "Risk settings");
      if (!response.ok) throw new Error(await response.text() || "Failed to load risk settings");
      return response.json();
    },
    { swr: true, ttlMs: 10 * 60 * 1000 },
  );
}

export async function updateRiskSettings(payload: any): Promise<any> {
  const response = await fetchWithDiagnostics("/workstation/risk-settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, "Update risk settings");
  if (!response.ok) throw new Error(await response.text() || "Failed to update risk settings");
  return response.json();
}

export async function fetchApiHealth(): Promise<any> {
  return cachedFetch(
    CACHE_KEYS.apiHealth,
    async () => {
      const response = await fetchWithDiagnostics("/workstation/api-health", undefined, "API health");
      if (!response.ok) throw new Error(await response.text() || "Failed to load API health");
      return response.json();
    },
    { swr: true, ttlMs: 2 * 60 * 1000, softTimeoutMs: 3000 },
  );
}

/** Invalidate paper-trading related caches after mutations. */
export function invalidatePaperCaches(): void {
  invalidateCache("paper_");
}
function formatAuthErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String((item as { msg: unknown }).msg) : String(item)))
      .join(", ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return fallback;
}

async function throwIfAuthFailed(response: Response, fallback: string): Promise<void> {
  if (response.ok) return;
  if ([502, 503, 504, 521, 522, 523, 524].includes(response.status)) {
    throw mapHttpError(response.status, response.url);
  }
  const errorData = await response.json().catch(() => null);
  throw new Error(formatAuthErrorDetail(errorData?.detail, fallback));
}

export async function authSignup(payload: any): Promise<any> {
  try {
    const response = await fetchWithDiagnostics(
      "/auth/signup",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      "Auth signup",
    );
    await throwIfAuthFailed(response, "Signup failed");
    return response.json();
  } catch (err) {
    throw err instanceof Error ? err : new Error(toUserFacingApiMessage(err, "Signup failed"));
  }
}

export async function authLogin(payload: any): Promise<any> {
  try {
    const response = await fetchWithDiagnostics(
      "/auth/login",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      "Auth login",
    );
    await throwIfAuthFailed(response, "Login failed");
    return response.json();
  } catch (err) {
    throw err instanceof Error ? err : new Error(toUserFacingApiMessage(err, "Login failed"));
  }
}

export async function authGoogleLogin(idToken: string): Promise<any> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetchWithDiagnostics(
      "/auth/google",
      {
        method: "POST",
        body: JSON.stringify({ id_token: idToken }),
        signal: controller.signal,
      },
      "Auth google",
    );
    await throwIfAuthFailed(response, "Google login failed");
    return response.json();
  } catch (err: any) {
    if (err?.name === "AbortError") {
      throw mapNetworkError(err, apiUrl("/auth/google"), "Auth google");
    }
    throw err instanceof Error ? err : new Error(toUserFacingApiMessage(err, "Google login failed"));
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function authMe(): Promise<any> {
  const response = await fetchWithDiagnostics("/auth/me", undefined, "Auth me");
  if (!response.ok) throw new Error("Not authenticated");
  return response.json();
}

/** Authenticated user profile (DB-backed — syncs across browsers/devices). */
export async function fetchUserProfile(opts?: { force?: boolean }): Promise<any> {
  return cachedFetch(
    "user_profile",
    async () => {
      const response = await fetchWithDiagnostics("/auth/profile", undefined, "User profile");
      if (!response.ok) throw new Error(await response.text() || "Failed to load profile");
      return response.json();
    },
    { force: opts?.force, swr: true, ttlMs: 60_000 },
  );
}

export async function updateUserProfile(payload: Record<string, unknown>): Promise<any> {
  const response = await fetchWithDiagnostics(
    "/auth/profile",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Update user profile",
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to update profile");
  }
  const data = await response.json();
  setCached("user_profile", data);
  return data;
}

export async function patchUserProfile(payload: Record<string, unknown>): Promise<any> {
  const response = await fetchWithDiagnostics(
    "/auth/profile",
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Patch user profile",
  );
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to update profile");
  }
  const data = await response.json();
  setCached("user_profile", data);
  return data;
}

export async function authLogout(): Promise<void> {
  try {
    await fetchWithDiagnostics("/auth/logout", { method: "POST" }, "Auth logout");
  } catch (err) {
    console.error(toUserFacingApiMessage(err));
  }
}

export async function forgotPassword(email: string): Promise<any> {
  try {
    const response = await fetchWithDiagnostics(
      "/auth/forgot-password",
      {
        method: "POST",
        body: JSON.stringify({ email }),
      },
      "Auth forgot password",
    );
    await throwIfAuthFailed(response, "Request failed");
    return response.json();
  } catch (err) {
    throw err instanceof Error ? err : new Error(toUserFacingApiMessage(err, "Request failed"));
  }
}

export async function resetPassword(token: string, password: string, confirmPassword: string): Promise<any> {
  try {
    const response = await fetchWithDiagnostics(
      "/auth/reset-password",
      {
        method: "POST",
        body: JSON.stringify({ token, password, confirm_password: confirmPassword }),
      },
      "Auth reset password",
    );
    await throwIfAuthFailed(response, "Password reset failed");
    return response.json();
  } catch (err) {
    throw err instanceof Error ? err : new Error(toUserFacingApiMessage(err, "Password reset failed"));
  }
}


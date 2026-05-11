import type {
  AnalysisMode,
  FullAnalysisResponse,
  PaperOrderActionResponse,
  PaperOrderTicketState,
  PaperPosition,
  PaperQuoteResponse,
  PaperTradingDashboardResponse,
  RecommendationPrefillRequest,
  RecommendationPrefillResponse,
  ScreenerResponse,
  TimeframeConfig,
  SymbolDetail,
} from "./types";

const PRIMARY_API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "https://trading-system-1efs.onrender.com";
const API_BASE_URLS = Array.from(new Set([PRIMARY_API_BASE_URL, "https://trading-system-1efs.onrender.com"]));
async function fetchWithDiagnostics(
  path: string,
  init: RequestInit | undefined,
  label: string,
): Promise<Response> {
  const attempts: string[] = [];
  let lastError: unknown = null;

  for (const baseUrl of API_BASE_URLS) {
    const url = `${baseUrl}${path}`;
    const startedAt = performance.now();
    attempts.push(url);
    const payloadPreview = typeof init?.body === "string" ? init.body : init?.body ? "[non-string body]" : "[no body]";
    console.info(`[api] ${label} -> ${url}`, {
      method: init?.method ?? "GET",
      payload: payloadPreview,
    });

    try {
      const response = await fetch(url, init);
      const elapsedMs = Math.round(performance.now() - startedAt);
      console.info(`[api] ${label} <- ${response.status} ${url} (${elapsedMs}ms)`);
      return response;
    } catch (error) {
      const elapsedMs = Math.round(performance.now() - startedAt);
      lastError = error;
      console.warn(`[api] ${label} network error at ${url} (${elapsedMs}ms)`, error);
    }
  }

  const reason = lastError instanceof Error ? lastError.message : String(lastError ?? "unknown network error");
  throw new Error(`${label} failed before reaching backend. Tried: ${attempts.join(", ")}. Last error: ${reason}`);
}

// `runFullAnalysis` removed — frontend uses `runPresetScreener` instead.

export async function runPresetScreener(
  mode: AnalysisMode,
  timeframe: TimeframeConfig,
  symbols: string[],
  topN: number,
): Promise<ScreenerResponse> {
  console.info("[scanner] runPresetScreener called", {
    mode,
    timeframe,
    symbolCount: symbols.length,
    topN,
  });
  const response = await fetchWithDiagnostics("/analysis/screener/full", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ mode, timeframe, symbols, top_n: topN }),
  }, "Scanner request");

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to run screener");
  }

  const payload = await response.json() as ScreenerResponse;
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

export async function fetchPaperTradingDashboard(selectedSymbol?: string): Promise<PaperTradingDashboardResponse> {
  const params = selectedSymbol ? `?selected_symbol=${encodeURIComponent(selectedSymbol)}` : "";
  const response = await fetchWithDiagnostics(`/paper-trading/dashboard${params}`, undefined, "Paper dashboard");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load paper trading dashboard");
  }
  return response.json() as Promise<PaperTradingDashboardResponse>;
}

export async function fetchPaperAccountSummary(): Promise<any> {
  const response = await fetchWithDiagnostics(`/paper-trading/account/summary`, undefined, "Paper account summary");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load account summary");
  }
  return response.json();
}

export async function fetchPaperQuote(symbol: string): Promise<PaperQuoteResponse> {
  const response = await fetchWithDiagnostics(`/paper-trading/symbols/${encodeURIComponent(symbol)}/quote`, undefined, "Paper quote");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load live paper trading quote");
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

export async function placePaperOrder(ticket: PaperOrderTicketState): Promise<PaperOrderActionResponse> {
  const response = await fetchWithDiagnostics("/paper-trading/orders", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      symbol: ticket.symbol,
      side: ticket.side,
      type: ticket.type,
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
    const message = await response.text();
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
  const response = await fetchWithDiagnostics("/analysis/scan/latest", undefined, "Load latest scan");
  if (!response.ok) {
    return null;
  }
  const data = await response.json() as ({ available?: boolean } & ScreenerResponse);
  if (!data.available) {
    return null;
  }
  return data as ScreenerResponse;
}

export async function fetchAnalytics(): Promise<any> {
  const response = await fetchWithDiagnostics(`/paper-trading/analytics`, undefined, "Paper analytics");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to load analytics");
  }
  return response.json();
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

export async function fetchNotifications(unread: boolean | null = null, limit = 10): Promise<{ id: number; message: string; level: string; is_read: boolean; created_at: string }[]> {
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

export async function fetchAlerts(): Promise<{ id: number; symbol: string; condition: string; target_price: number; status: string; created_at: string; triggered_at?: string | null; triggered_price?: number | null }[]> {
  const response = await fetchWithDiagnostics(`/paper-trading/alerts`, undefined, "Fetch alerts");
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to fetch alerts");
  }
  return response.json();
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

// Token management API for FYERS refresh flow
export async function saveAccessToken(access_token: string, note?: string) {
  const body: any = { access_token };
  if (note) body.note = note;
  const response = await fetchWithDiagnostics('/api/token/save-access-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, 'Save access token');
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || 'Failed to save access token');
  }
  return response.json();
}

export async function getTokenStatus() {
  const response = await fetchWithDiagnostics('/api/token/status', undefined, 'Token status');
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || 'Failed to get token status');
  }
  return response.json();
}
export async function getTokenHistory(limit = 50) {
  const response = await fetchWithDiagnostics(`/api/token/history?limit=${encodeURIComponent(String(limit))}`, undefined, 'Token history');
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || 'Failed to get token history');
  }
  return response.json();
}

export async function fetchUniverses(): Promise<{ name: string; symbols: string[]; count: number }[]> {
  const response = await fetchWithDiagnostics("/workstation/universes", undefined, "Universes");
  if (!response.ok) throw new Error(await response.text() || "Failed to load universes");
  return response.json();
}

export async function fetchMarketOverview(): Promise<any> {
  const response = await fetchWithDiagnostics("/workstation/market-overview", undefined, "Market overview");
  if (!response.ok) throw new Error(await response.text() || "Failed to load market overview");
  return response.json();
}

export async function fetchSavedScans(): Promise<any[]> {
  const response = await fetchWithDiagnostics("/workstation/saved-scans", undefined, "Saved scans");
  if (!response.ok) throw new Error(await response.text() || "Failed to load saved scans");
  return response.json();
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
  const response = await fetchWithDiagnostics("/workstation/alerts", undefined, "Workstation alerts");
  if (!response.ok) throw new Error(await response.text() || "Failed to load alerts");
  return response.json();
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
  const response = await fetchWithDiagnostics("/workstation/risk-settings", undefined, "Risk settings");
  if (!response.ok) throw new Error(await response.text() || "Failed to load risk settings");
  return response.json();
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
  const response = await fetchWithDiagnostics("/workstation/api-health", undefined, "API health");
  if (!response.ok) throw new Error(await response.text() || "Failed to load API health");
  return response.json();
}

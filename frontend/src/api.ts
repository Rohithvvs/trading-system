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
} from "./types";

const PRIMARY_API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
const API_BASE_URLS = Array.from(new Set([PRIMARY_API_BASE_URL, "http://127.0.0.1:8001"]));

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
    console.info(`[api] ${label} -> ${url}`);

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

export async function runFullAnalysis(
  symbols: string[],
  mode: AnalysisMode,
  timeframe: TimeframeConfig,
): Promise<FullAnalysisResponse> {
  const response = await fetchWithDiagnostics("/analysis/full", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ symbols, mode, timeframe }),
  }, "Full analysis");

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || "Failed to analyze stocks");
  }

  return response.json() as Promise<FullAnalysisResponse>;
}

export async function runPresetScreener(
  mode: AnalysisMode,
  timeframe: TimeframeConfig,
  symbols: string[],
  topN: number,
): Promise<ScreenerResponse> {
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

  return response.json() as Promise<ScreenerResponse>;
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

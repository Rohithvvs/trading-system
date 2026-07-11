/** Phase 1 retail trading platform API client — wired to real backend routes. */
import { apiUrl, getWsBaseUrl } from "./config";

const JSON_HEADERS = {
  "Content-Type": "application/json",
  Accept: "application/json",
} as const;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    credentials: "include",
    headers: { ...JSON_HEADERS, ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* ignore */
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────────────

export type WatchlistItem = {
  id: number;
  symbol: string;
  exchange: string;
  sort_order: number;
  notes?: string | null;
  company_name?: string | null;
  sector?: string | null;
  ltp?: number | null;
  change?: number | null;
  change_pct?: number | null;
  volume?: number | null;
  created_at: string;
};

export type Watchlist = {
  id: number;
  name: string;
  sort_order: number;
  is_pinned: boolean;
  is_favorite: boolean;
  sort_by: string;
  item_count: number;
  items: WatchlistItem[];
  created_at: string;
  updated_at: string;
};

export type QuoteBoardItem = {
  symbol: string;
  company_name?: string | null;
  sector?: string | null;
  ltp?: number | null;
  change?: number | null;
  change_pct?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  vwap?: number | null;
  volume?: number | null;
  bid?: number | null;
  ask?: number | null;
  bid_qty?: number | null;
  ask_qty?: number | null;
  upper_circuit?: number | null;
  lower_circuit?: number | null;
  market_status: string;
  source: string;
};

export type QuoteBoardResponse = {
  items: QuoteBoardItem[];
  total: number;
  page: number;
  page_size: number;
  market_status: string;
  updated_at: string;
};

export type IndexQuote = {
  symbol: string;
  label: string;
  ltp?: number | null;
  change?: number | null;
  change_pct?: number | null;
  sparkline: number[];
  source: string;
};

export type IndicesStripResponse = {
  indices: IndexQuote[];
  market_status: string;
  updated_at: string;
};

export type HeatmapResponse = {
  group_by: string;
  sectors: {
    sector: string;
    change_pct?: number | null;
    stocks: { symbol: string; name: string; change_pct?: number | null; ltp?: number | null }[];
    stock_count: number;
  }[];
  updated_at: string;
};

export type SymbolSearchResult = {
  symbol: string;
  company_name?: string | null;
  exchange?: string;
  sector?: string | null;
  industry?: string | null;
  isin?: string | null;
  instrument_type?: string;
  is_favorite?: boolean;
};

export type SymbolSearchResponse = {
  results: SymbolSearchResult[];
  recent: SymbolSearchResult[];
  trending: SymbolSearchResult[];
  favorites: SymbolSearchResult[];
  query: string;
  total: number;
};

export type ChartCandle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type ChartDataResponse = {
  symbol: string;
  timeframe: string;
  candles: ChartCandle[];
  indicators: Record<string, unknown>;
  source: string;
  updated_at: string;
};

export type NotificationItem = {
  id: number;
  category: string;
  title: string;
  body: string;
  level: string;
  symbol?: string | null;
  is_read: boolean;
  created_at: string;
};

export type NotificationListResponse = {
  items: NotificationItem[];
  total: number;
  unread_count: number;
  page: number;
  page_size: number;
};

export type HoldingsResponse = {
  holdings: {
    symbol: string;
    qty: number;
    avg_price: number;
    ltp: number;
    invested: number;
    current_value: number;
    pnl: number;
    pnl_pct: number;
    day_pnl: number;
    day_pnl_pct: number;
    sector?: string | null;
  }[];
  total_invested: number;
  total_current_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  todays_pnl: number;
  allocation: { symbol: string; value: number; pct: number }[];
  sector_exposure: { sector: string; value: number; pct: number }[];
};

export type PositionsResponse = {
  open: PositionRow[];
  closed: PositionRow[];
  intraday: PositionRow[];
  carry_forward: PositionRow[];
  total_mtm: number;
  total_risk: number;
};

export type PositionRow = {
  id: number;
  symbol: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  invested_value: number;
  product_type: string;
  position_type: string;
  stop_loss?: number | null;
  target?: number | null;
  risk_reward?: number | null;
  created_at: string;
  updated_at: string;
};

export type OrdersPageResponse = {
  items: {
    id: number;
    symbol: string;
    side: string;
    type: string;
    product_type?: string | null;
    qty: number;
    price?: number | null;
    stop_price?: number | null;
    status: string;
    lifecycle_state: string;
    filled_price?: number | null;
    created_at: string;
    filled_at?: string | null;
    notes?: string | null;
  }[];
  total: number;
  page: number;
  page_size: number;
  pending: number;
  executed: number;
  rejected: number;
  cancelled: number;
};

export type OrderPreviewResponse = {
  symbol: string;
  side: string;
  type: string;
  product_type: string;
  validity: string;
  qty: number;
  estimated_price: number;
  order_value: number;
  charges: {
    brokerage: number;
    stt: number;
    exchange_txn: number;
    sebi_fees: number;
    gst: number;
    stamp_duty: number;
    total_charges: number;
  };
  taxes_total: number;
  margin_required: number;
  funds_required: number;
  available_funds: number;
  expected_pnl?: number | null;
  risk_reward?: number | null;
  risk_checks: { code: string; passed: boolean; message: string }[];
  can_place: boolean;
  reject_reasons: string[];
  circuit_status?: string | null;
  freeze_qty?: number | null;
};

export type RiskLimits = {
  max_daily_loss: number;
  max_trade_loss: number;
  max_position_size: number;
  max_exposure: number;
  max_sector_exposure_pct: number;
  max_leverage: number;
  max_open_positions: number;
  enabled: boolean;
  daily_pnl?: number;
  current_exposure?: number;
  open_positions?: number;
};

// ── Watchlists ───────────────────────────────────────────────────────────────

export const fetchWatchlists = (search?: string) =>
  request<Watchlist[]>(`/watchlists${search ? `?search=${encodeURIComponent(search)}` : ""}`);

export const createWatchlist = (name: string, symbols: string[] = []) =>
  request<Watchlist>("/watchlists", { method: "POST", body: JSON.stringify({ name, symbols }) });

export const updateWatchlist = (id: number, body: Partial<{ name: string; is_pinned: boolean; is_favorite: boolean; sort_by: string }>) =>
  request<Watchlist>(`/watchlists/${id}`, { method: "PUT", body: JSON.stringify(body) });

export const deleteWatchlist = (id: number) =>
  request<{ deleted: number }>(`/watchlists/${id}`, { method: "DELETE" });

export const reorderWatchlists = (ordered_ids: number[]) =>
  request<Watchlist[]>("/watchlists/reorder", { method: "PUT", body: JSON.stringify({ ordered_ids }) });

export const addWatchlistItem = (id: number, symbol: string) =>
  request<Watchlist>(`/watchlists/${id}/items`, { method: "POST", body: JSON.stringify({ symbol }) });

export const removeWatchlistItem = (wlId: number, itemId: number) =>
  request<Watchlist>(`/watchlists/${wlId}/items/${itemId}`, { method: "DELETE" });

export const reorderWatchlistItems = (wlId: number, ordered_item_ids: number[]) =>
  request<Watchlist>(`/watchlists/${wlId}/items/reorder`, {
    method: "PUT",
    body: JSON.stringify({ ordered_item_ids }),
  });

export const importWatchlist = (symbols: string[], name?: string) =>
  request<Watchlist>("/watchlists/import", { method: "POST", body: JSON.stringify({ symbols, name }) });

export const exportWatchlist = (id: number) =>
  request<{ name: string; symbols: string[]; exported_at: string }>(`/watchlists/${id}/export`);

// ── Market ───────────────────────────────────────────────────────────────────

export const fetchQuoteBoard = (params: {
  search?: string;
  sector?: string;
  sort_by?: string;
  sort_dir?: string;
  page?: number;
  page_size?: number;
}) => {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") sp.set(k, String(v));
  });
  return request<QuoteBoardResponse>(`/market/quote-board?${sp}`);
};

export const fetchIndices = () => request<IndicesStripResponse>("/market/indices");

export const fetchHeatmap = (group_by = "sector") =>
  request<HeatmapResponse>(`/market/heatmap?group_by=${group_by}`);

export const fetchBatchQuotes = (symbols: string[]) =>
  request<Record<string, Record<string, number | string | null>>>(
    `/market/quotes?symbols=${encodeURIComponent(symbols.join(","))}`,
  );

// ── Search ───────────────────────────────────────────────────────────────────

export const searchSymbols = (q: string, limit = 20) =>
  request<SymbolSearchResponse>(`/search/symbols?q=${encodeURIComponent(q)}&limit=${limit}`);

export const recordSymbolSearch = (symbol: string) =>
  request(`/search/symbols/${encodeURIComponent(symbol)}/record`, { method: "POST" });

export const addFavoriteSymbol = (symbol: string) =>
  request(`/search/favorites/${encodeURIComponent(symbol)}`, { method: "POST" });

export const removeFavoriteSymbol = (symbol: string) =>
  request(`/search/favorites/${encodeURIComponent(symbol)}`, { method: "DELETE" });

// ── Charts ───────────────────────────────────────────────────────────────────

export const fetchChartData = (symbol: string, timeframe = "1D", indicators?: string) => {
  const sp = new URLSearchParams({ timeframe });
  if (indicators) sp.set("indicators", indicators);
  return request<ChartDataResponse>(`/charts/${encodeURIComponent(symbol)}?${sp}`);
};

export const fetchChartLayouts = () => request<{ id: number; name: string; symbol: string; timeframe: string }[]>("/charts/layouts/list");

export const saveChartLayout = (body: {
  name: string;
  symbol: string;
  timeframe: string;
  chart_type: string;
  theme: string;
  indicators: unknown[];
  drawings: unknown[];
  is_default?: boolean;
}) => request("/charts/layouts", { method: "POST", body: JSON.stringify(body) });

// ── Notifications ────────────────────────────────────────────────────────────

export const fetchNotifications = (params?: { category?: string; search?: string; unread_only?: boolean; page?: number }) => {
  const sp = new URLSearchParams();
  if (params?.category) sp.set("category", params.category);
  if (params?.search) sp.set("search", params.search);
  if (params?.unread_only) sp.set("unread_only", "true");
  if (params?.page) sp.set("page", String(params.page));
  return request<NotificationListResponse>(`/notifications?${sp}`);
};

export const fetchUnreadCount = () => request<{ unread_count: number }>("/notifications/unread-count");

export const markAllNotificationsRead = () =>
  request("/notifications/mark-all-read", { method: "POST" });

export const markNotifications = (ids: number[], mark_read = true) =>
  request("/notifications/mark", { method: "POST", body: JSON.stringify({ ids, mark_read }) });

export const deleteNotifications = (ids: number[]) =>
  request(`/notifications?ids=${ids.join(",")}`, { method: "DELETE" });

// ── Portfolio ────────────────────────────────────────────────────────────────

export const fetchHoldings = () => request<HoldingsResponse>("/holdings");
export const fetchPositionsView = () => request<PositionsResponse>("/positions");
export const fetchOrdersPage = (params?: { status?: string; search?: string; page?: number }) => {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  if (params?.search) sp.set("search", params.search);
  if (params?.page) sp.set("page", String(params.page));
  return request<OrdersPageResponse>(`/orders?${sp}`);
};

// ── Order ticket / risk ──────────────────────────────────────────────────────

export const previewOrder = (body: Record<string, unknown>) =>
  request<OrderPreviewResponse>("/order-ticket/preview", { method: "POST", body: JSON.stringify(body) });

export const fetchRiskLimits = () => request<RiskLimits>("/risk/limits");

export const updateRiskLimits = (body: Partial<RiskLimits>) =>
  request<RiskLimits>("/risk/limits", { method: "PUT", body: JSON.stringify(body) });

// ── WebSocket ────────────────────────────────────────────────────────────────

export function connectQuotesWs(
  onQuotes: (data: Record<string, Record<string, unknown>>) => void,
  onStatus?: (s: "open" | "closed" | "error") => void,
) {
  const url = `${getWsBaseUrl()}/ws/quotes`;
  let ws: WebSocket | null = null;
  let closed = false;
  let heartbeat: ReturnType<typeof setInterval> | null = null;
  let retryMs = 1000;

  const connect = () => {
    if (closed) return;
    ws = new WebSocket(url);
    ws.onopen = () => {
      retryMs = 1000;
      onStatus?.("open");
      heartbeat = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action: "ping" }));
      }, 15000);
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "quotes" && msg.data) onQuotes(msg.data);
      } catch {
        /* ignore */
      }
    };
    ws.onerror = () => onStatus?.("error");
    ws.onclose = () => {
      onStatus?.("closed");
      if (heartbeat) clearInterval(heartbeat);
      if (!closed) {
        setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, 15000);
      }
    };
  };

  connect();

  return {
    subscribe(symbols: string[]) {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "subscribe", symbols }));
      } else {
        const socket = ws;
        if (socket) {
          const prev = socket.onopen;
          socket.onopen = (ev) => {
            if (typeof prev === "function") prev.call(socket, ev);
            socket.send(JSON.stringify({ action: "subscribe", symbols }));
          };
        }
      }
    },
    unsubscribe(symbols: string[]) {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "unsubscribe", symbols }));
      }
    },
    close() {
      closed = true;
      if (heartbeat) clearInterval(heartbeat);
      ws?.close();
    },
  };
}

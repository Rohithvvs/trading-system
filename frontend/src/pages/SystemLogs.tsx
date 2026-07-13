import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, apiUrl } from "../config";

type SystemLog = {
  id?: number;
  timestamp?: string;
  level: string;
  source?: string;
  module?: string;
  endpoint?: string | null;
  message: string;
  error_hash?: string | null;
  traceback?: string | null;
  structured_data?: unknown;
  correlationId?: string | null;
  symbol?: string | null;
  environment?: string | null;
};

type Filters = {
  level: string;
  symbol: string;
  correlationId: string;
  error_hash: string;
  environment: string;
  dateFrom: string;
  dateTo: string;
};

const EMPTY_FILTERS: Filters = {
  level: "",
  symbol: "",
  correlationId: "",
  error_hash: "",
  environment: "",
  dateFrom: "",
  dateTo: "",
};

function buildQuery(filters: Filters) {
  const params = new URLSearchParams();
  params.set("limit", "500");
  Object.entries(filters).forEach(([key, value]) => {
    if (value.trim()) {
      if (key === "dateFrom" || key === "dateTo") {
        try {
          params.set(key, new Date(value).toISOString());
        } catch {
          params.set(key, value.trim());
        }
      } else {
        params.set(key, value.trim());
      }
    }
  });
  return params.toString();
}

function websocketUrl() {
  const base = new URL(API_BASE_URL || window.location.origin, window.location.href);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = "/api/logs/stream";
  base.search = "";
  return base.toString();
}

function levelClass(level: string) {
  const normalized = level.toUpperCase();
  if (normalized === "CRITICAL" || normalized === "ERROR") return "text-red-500";
  if (normalized === "WARN" || normalized === "WARNING") return "text-yellow-500";
  if (normalized === "INFO" || normalized === "SUCCESS") return "text-green-500";
  return "text-gray-500";
}

export function SystemLogs() {
  const [logs, setLogs] = useState<SystemLog[]>([]);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<"connecting" | "live" | "reconnecting" | "offline">("connecting");
  const [clearOpen, setClearOpen] = useState(false);
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const filtersRef = useRef<Filters>(filters);

  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  const query = useMemo(() => buildQuery(filters), [filters]);

  const loadLogs = useCallback(async () => {
    const response = await fetch(apiUrl(`/api/logs?${query}`), { credentials: "include" });
    if (!response.ok) throw new Error(await response.text());
    setLogs(await response.json());
  }, [query]);

  useEffect(() => {
    void loadLogs().catch((error) => console.warn("Failed to load system logs", error));
  }, [loadLogs]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closedByEffect = false;

    function connect() {
      setStatus(reconnectAttemptRef.current > 0 ? "reconnecting" : "connecting");
      socket = new WebSocket(websocketUrl());

      socket.onopen = () => {
        reconnectAttemptRef.current = 0;
        setStatus("live");
      };

      socket.onmessage = (event) => {
        const next = JSON.parse(event.data) as SystemLog;
        const currentFilters = filtersRef.current;
        
        if (currentFilters.level && next.level.toUpperCase() !== currentFilters.level.toUpperCase()) return;
        if (currentFilters.symbol && next.symbol !== currentFilters.symbol) return;
        if (currentFilters.correlationId && next.correlationId !== currentFilters.correlationId) return;
        if (currentFilters.error_hash && next.error_hash !== currentFilters.error_hash) return;
        if (currentFilters.environment && next.environment?.toUpperCase() !== currentFilters.environment.toUpperCase()) return;
        
        if (currentFilters.dateFrom) {
          const from = new Date(currentFilters.dateFrom).getTime();
          if (next.timestamp && new Date(next.timestamp).getTime() < from) return;
        }
        
        if (currentFilters.dateTo) {
          const to = new Date(currentFilters.dateTo).getTime();
          if (next.timestamp && new Date(next.timestamp).getTime() > to) return;
        }
        
        setLogs((current) => [next, ...current].slice(0, 1000));
      };

      socket.onclose = () => {
        if (closedByEffect) return;
        setStatus("reconnecting");
        const attempt = reconnectAttemptRef.current + 1;
        reconnectAttemptRef.current = attempt;
        const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5));
        reconnectTimerRef.current = window.setTimeout(connect, delay);
      };

      socket.onerror = () => {
        setStatus("offline");
        socket?.close();
      };
    }

    connect();
    return () => {
      closedByEffect = true;
      if (reconnectTimerRef.current !== null) window.clearTimeout(reconnectTimerRef.current);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (typeof terminalRef.current?.scrollTo === "function") {
      terminalRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [logs.length]);

  async function clearLogs() {
    try {
      const response = await fetch(apiUrl("/api/logs/clear?confirm=WIPE_ALL&days_old=0"), {
        method: "DELETE",
        credentials: "include",
      });
      if (!response.ok) {
        const errText = await response.text();
        window.dispatchEvent(
          new CustomEvent("app:toast", {
            detail: { level: "error", message: "Failed to clear logs", description: errText },
          }),
        );
        return;
      }
      setLogs([]);
      setClearOpen(false);
      window.dispatchEvent(
        new CustomEvent("app:toast", {
          detail: { level: "success", message: "Logs cleared" },
        }),
      );
    } catch (err) {
      window.dispatchEvent(
        new CustomEvent("app:toast", {
          detail: { level: "error", message: "Network error while clearing logs", description: String(err) },
        }),
      );
    }
  }

  const exportUrl = apiUrl(`/api/logs/export?${query}`);

  return (
    <main className="logs-page" data-testid="system-logs-page">
      <section className="logs-toolbar">
        <div>
          <p className="section-label">Forensic terminal</p>
          <h1>System Logs</h1>
        </div>
        <div className="logs-actions">
          <span className={`logs-connection ${status}`}>{status}</span>
          <a className="button ghost-button" href={`${exportUrl}&format=csv`}>Export CSV</a>
          <a className="button ghost-button" href={`${exportUrl}&format=json`}>Export JSON</a>
          <button type="button" className="button danger-button" onClick={() => setClearOpen(true)}>Clear Logs</button>
        </div>
      </section>

      <section className="logs-filter-panel">
        <select value={filters.level} onChange={(event) => setFilters((current) => ({ ...current, level: event.target.value }))}>
          <option value="">All levels</option>
          {["CRITICAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"].map((level) => <option key={level}>{level}</option>)}
        </select>
        <input placeholder="Symbol" value={filters.symbol} onChange={(event) => setFilters((current) => ({ ...current, symbol: event.target.value }))} />
        <input placeholder="Correlation ID" value={filters.correlationId} onChange={(event) => setFilters((current) => ({ ...current, correlationId: event.target.value }))} />
        <input placeholder="Error hash" value={filters.error_hash} onChange={(event) => setFilters((current) => ({ ...current, error_hash: event.target.value }))} />
        <input placeholder="Environment" value={filters.environment} onChange={(event) => setFilters((current) => ({ ...current, environment: event.target.value }))} />
        <input type="datetime-local" value={filters.dateFrom} onChange={(event) => setFilters((current) => ({ ...current, dateFrom: event.target.value }))} />
        <input type="datetime-local" value={filters.dateTo} onChange={(event) => setFilters((current) => ({ ...current, dateTo: event.target.value }))} />
        <button type="button" className="button ghost-button" onClick={() => setFilters(EMPTY_FILTERS)}>Reset</button>
      </section>

      <section ref={terminalRef} className="logs-terminal" data-testid="logs-terminal">
        {logs.map((log, index) => {
          const key = String(log.id ?? `${log.timestamp}-${index}`);
          const isExpanded = Boolean(expanded[key]);
          return (
            <article key={key} className="log-line" data-testid="log-line">
              <button
                type="button"
                className="log-line-main"
                aria-label={`View Stacktrace for ${log.message}`}
                onClick={() => setExpanded((current) => ({ ...current, [key]: !isExpanded }))}
              >
                <span className="log-time">{log.timestamp ? new Date(log.timestamp).toLocaleString() : "--"}</span>
                <span className={`log-level ${levelClass(log.level)}`}>{log.level}</span>
                <span className="log-source">{log.source ?? "SYSTEM"}</span>
                <span className="log-module">{log.module ?? "unknown"}</span>
                <span className="log-message">{log.message}</span>
              </button>
              {isExpanded ? (
                <div className="log-details" data-testid="log-details">
                  <pre>{JSON.stringify(log.structured_data ?? {}, null, 2)}</pre>
                  {log.traceback ? <pre>{log.traceback}</pre> : null}
                  <p>{log.correlationId ? `cid=${log.correlationId}` : "cid=none"} {log.error_hash ? `hash=${log.error_hash}` : ""}</p>
                </div>
              ) : null}
            </article>
          );
        })}
        {!logs.length ? <div className="logs-empty">No logs match the current filters.</div> : null}
      </section>

      {clearOpen ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="confirm-modal">
            <h2>Clear all logs?</h2>
            <p>This removes every row from the system log ledger for this environment.</p>
            <div className="modal-actions">
              <button type="button" className="button ghost-button" onClick={() => setClearOpen(false)}>Cancel</button>
              <button type="button" className="button danger-button" onClick={() => void clearLogs()}>Confirm Clear</button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

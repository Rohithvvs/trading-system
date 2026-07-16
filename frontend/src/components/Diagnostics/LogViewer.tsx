import { useCallback, useEffect, useState } from "react";
import { diagnosticsFetch } from "./diagnosticsFetch";

interface LogEntry {
  timestamp: string;
  level: string;
  source: string;
  message: string;
  metadata?: Record<string, unknown>;
}

interface LogViewerProps {
  apiBaseUrl: string;
}

const LEVELS = ["", "debug", "info", "warning", "error", "critical"];

export function LogViewer({ apiBaseUrl }: LogViewerProps) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [level, setLevel] = useState("");
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      setError(null);
      const params = new URLSearchParams();
      if (level) params.set("level", level);
      if (source) params.set("source", source);
      params.set("limit", "100");
      const res = await diagnosticsFetch(`${apiBaseUrl}/api/v1/dashboard/logs?${params}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEntries(data.entries || []);
    } catch (err: any) {
      setError(err.message || "Backend unreachable");
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, level, source]);

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  return (
    <section className="panel">
      <h3 className="ds-title">Log Viewer</h3>
      <div className="log-filters">
        <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Filter by level">
          {LEVELS.map((l) => (
            <option key={l} value={l}>
              {l || "All levels"}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Filter by source..."
          value={source}
          onChange={(e) => setSource(e.target.value)}
          aria-label="Filter by source"
        />
        <button type="button" className="button ghost-button" onClick={fetchLogs}>
          Refresh
        </button>
      </div>

      {error ? (
        <div className="error-state" role="alert">
          <p>{error}</p>
          <button type="button" className="button primary-button" onClick={fetchLogs}>
            Retry
          </button>
        </div>
      ) : loading ? (
        <p className="ds-caption">Loading logs...</p>
      ) : entries.length === 0 ? (
        <p className="ds-caption">No log entries found.</p>
      ) : (
        <div className="log-table-wrapper" style={{ maxHeight: 400, overflowY: "auto" }}>
          <table className="log-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Level</th>
                <th>Source</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, i) => (
                <tr key={i} className={`log-row log-row--${entry.level}`}>
                  <td className="log-timestamp">
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </td>
                  <td>
                    <span className={`ds-badge ds-badge--${entry.level}`}>
                      {entry.level}
                    </span>
                  </td>
                  <td className="log-source">{entry.source}</td>
                  <td className="log-message">{entry.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

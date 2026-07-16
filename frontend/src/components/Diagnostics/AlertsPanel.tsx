import { useEffect, useState } from "react";
import { diagnosticsFetch } from "./diagnosticsFetch";

interface AlertEntry {
  uuid: string;
  rule_name: string;
  severity: string;
  metric_name: string;
  metric_value: number;
  threshold: number;
  message: string | null;
  timestamp: string;
}

interface AlertsPanelProps {
  apiBaseUrl: string;
}

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  warning: 1,
  info: 2,
};

export function AlertsPanel({ apiBaseUrl }: AlertsPanelProps) {
  const [alerts, setAlerts] = useState<AlertEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchAlerts() {
    try {
      setError(null);
      const res = await diagnosticsFetch(`${apiBaseUrl}/api/v1/dashboard/alerts`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const sorted = (data.alerts || []).sort(
        (a: AlertEntry, b: AlertEntry) =>
          (SEVERITY_ORDER[a.severity] ?? 2) - (SEVERITY_ORDER[b.severity] ?? 2),
      );
      setAlerts(sorted);
    } catch (err: any) {
      setError(err.message || "Backend unreachable");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 5000);
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  return (
    <section className="panel">
      <h3 className="ds-title">Active Alerts</h3>
      {error ? (
        <div className="error-state" role="alert">
          <p>{error}</p>
          <button type="button" className="button primary-button" onClick={fetchAlerts}>
            Retry
          </button>
        </div>
      ) : loading ? (
        <p className="ds-caption">Loading alerts...</p>
      ) : alerts.length === 0 ? (
        <p className="ds-caption">No active alerts.</p>
      ) : (
        <ul className="alert-list">
          {alerts.map((alert) => (
            <li key={alert.uuid} className={`alert-item alert-item--${alert.severity}`}>
              <div className="alert-header">
                <span className={`ds-badge ds-badge--${alert.severity}`}>
                  {alert.severity.toUpperCase()}
                </span>
                <strong>{alert.rule_name}</strong>
              </div>
              <p className="alert-message">
                {alert.message || `${alert.metric_name} = ${alert.metric_value} (threshold: ${alert.threshold})`}
              </p>
              <span className="ds-caption">
                {new Date(alert.timestamp).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

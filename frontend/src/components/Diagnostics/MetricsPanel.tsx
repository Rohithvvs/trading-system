import { useEffect, useState } from "react";
import { diagnosticsFetch } from "./diagnosticsFetch";

interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_used_mb: number;
  request_rate_per_sec: number;
  error_rate_per_sec: number;
}

interface MetricsPanelProps {
  apiBaseUrl: string;
}

export function MetricsPanel({ apiBaseUrl }: MetricsPanelProps) {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchMetrics() {
    try {
      setError(null);
      const res = await diagnosticsFetch(`${apiBaseUrl}/api/v1/dashboard/metrics`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setMetrics(data.system);
    } catch (err: any) {
      setError(err.message || "Backend unreachable");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 5000);
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  if (error) {
    return (
      <section className="panel">
        <h3 className="ds-title">System Metrics</h3>
        <div className="error-state" role="alert">
          <p>{error}</p>
          <button type="button" className="button primary-button" onClick={fetchMetrics}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  if (loading || !metrics) {
    return (
      <section className="panel">
        <h3 className="ds-title">System Metrics</h3>
        <p className="ds-caption">Loading metrics...</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h3 className="ds-title">System Metrics</h3>
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-label">CPU</span>
          <span className="metric-value">{metrics.cpu_percent.toFixed(1)}%</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Memory</span>
          <span className="metric-value">{metrics.memory_percent.toFixed(1)}%</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Memory Used</span>
          <span className="metric-value">{metrics.memory_used_mb.toFixed(0)} MB</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Request Rate</span>
          <span className="metric-value">{metrics.request_rate_per_sec.toFixed(1)}/s</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Error Rate</span>
          <span className="metric-value">{metrics.error_rate_per_sec.toFixed(1)}/s</span>
        </div>
      </div>
    </section>
  );
}

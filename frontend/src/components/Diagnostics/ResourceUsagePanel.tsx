import { useEffect, useState } from "react";
import { diagnosticsFetch } from "./diagnosticsFetch";

interface ExperimentData {
  id: string;
  name: string;
  cpu_percent: number;
  memory_percent: number;
  io_read_bytes_per_sec: number;
  io_write_bytes_per_sec: number;
}

interface ResourceUsagePanelProps {
  apiBaseUrl: string;
}

export function ResourceUsagePanel({ apiBaseUrl }: ResourceUsagePanelProps) {
  const [experiment, setExperiment] = useState<ExperimentData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchUsage() {
    try {
      setError(null);
      const res = await diagnosticsFetch(`${apiBaseUrl}/api/v1/dashboard/metrics`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setExperiment(data.experiment || null);
    } catch (err: any) {
      setError(err.message || "Backend unreachable");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchUsage();
    const interval = setInterval(fetchUsage, 5000);
    return () => clearInterval(interval);
  }, [apiBaseUrl]);

  if (error) {
    return (
      <section className="panel">
        <h3 className="ds-title">Experiment Resource Usage</h3>
        <div className="error-state" role="alert">
          <p>{error}</p>
          <button type="button" className="button primary-button" onClick={fetchUsage}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  if (!experiment) {
    return (
      <section className="panel" aria-disabled="true">
        <h3 className="ds-title">Experiment Resource Usage</h3>
        <p className="ds-caption">No active experiment.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h3 className="ds-title">
        Experiment: {experiment.name}
      </h3>
      <div className="metrics-grid">
        <div className="metric-card">
          <span className="metric-label">CPU</span>
          <span className="metric-value">{experiment.cpu_percent.toFixed(1)}%</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Memory</span>
          <span className="metric-value">{experiment.memory_percent.toFixed(1)}%</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">I/O Read</span>
          <span className="metric-value">
            {(experiment.io_read_bytes_per_sec / 1024).toFixed(1)} KB/s
          </span>
        </div>
        <div className="metric-card">
          <span className="metric-label">I/O Write</span>
          <span className="metric-value">
            {(experiment.io_write_bytes_per_sec / 1024).toFixed(1)} KB/s
          </span>
        </div>
      </div>
    </section>
  );
}

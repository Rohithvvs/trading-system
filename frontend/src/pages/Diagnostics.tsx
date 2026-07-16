import { useMemo } from "react";
import { MetricsPanel } from "../components/Diagnostics/MetricsPanel";
import { LogViewer } from "../components/Diagnostics/LogViewer";
import { AlertsPanel } from "../components/Diagnostics/AlertsPanel";
import { ResourceUsagePanel } from "../components/Diagnostics/ResourceUsagePanel";
import { API_BASE_URL } from "../config";

export function DiagnosticsPage() {
  const apiBaseUrl = useMemo(() => API_BASE_URL || "", []);

  return (
    <main className="page-container">
      <h1 className="ds-title page-title">Diagnostics Dashboard</h1>
      <div className="diagnostics-grid">
        <div className="diagnostics-grid__main">
          <MetricsPanel apiBaseUrl={apiBaseUrl} />
          <LogViewer apiBaseUrl={apiBaseUrl} />
        </div>
        <div className="diagnostics-grid__side">
          <AlertsPanel apiBaseUrl={apiBaseUrl} />
          <ResourceUsagePanel apiBaseUrl={apiBaseUrl} />
        </div>
      </div>
    </main>
  );
}

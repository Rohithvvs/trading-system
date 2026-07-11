import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { ChartSkeleton, PanelSkeleton } from "../../components/Skeleton";

const WorkstationPage = lazy(() =>
  import("../../components/WorkstationPage").then((m) => ({ default: m.WorkstationPage })),
);

export function DashboardPage() {
  return (
    <div className="retail-page">
      <div className="quick-links panel" style={{ marginBottom: 12, display: "flex", flexWrap: "wrap", gap: 8, padding: 12 }}>
        <Link className="button ghost-button" to="/watchlists">Watchlists</Link>
        <Link className="button ghost-button" to="/quotes">Quote board</Link>
        <Link className="button ghost-button" to="/chart">Charts</Link>
        <Link className="button ghost-button" to="/holdings">Holdings</Link>
        <Link className="button ghost-button" to="/positions">Positions</Link>
        <Link className="button ghost-button" to="/orders">Orders</Link>
        <Link className="button ghost-button" to="/heatmap">Heatmap</Link>
        <Link className="button ghost-button" to="/scanner">Scanner</Link>
        <Link className="button ghost-button" to="/paper-trading">Trade</Link>
        <Link className="button ghost-button" to="/alerts">Alerts</Link>
      </div>
      <Suspense
        fallback={
          <div className="dashboard-grid" style={{ padding: 16 }}>
            <PanelSkeleton title="Loading dashboard">
              <ChartSkeleton height={120} />
            </PanelSkeleton>
          </div>
        }
      >
        <WorkstationPage onLoadSavedScan={() => undefined} />
      </Suspense>
    </div>
  );
}

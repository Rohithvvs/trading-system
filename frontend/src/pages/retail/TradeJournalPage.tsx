import { lazy, Suspense } from "react";
import { PanelSkeleton, ChartSkeleton } from "../../components/Skeleton";

const DailyAnalyticsPanel = lazy(() =>
  import("../../components/DailyAnalyticsPanel").then((m) => ({ default: m.DailyAnalyticsPanel })),
);

/** Trade journal — reuses production daily analytics / journal backend integration. */
export function TradeJournalPage() {
  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Trade journal</p>
            <h2>Journal, emotions, lessons & analytics</h2>
          </div>
        </div>
        <Suspense
          fallback={
            <PanelSkeleton title="Loading journal">
              <ChartSkeleton height={160} />
            </PanelSkeleton>
          }
        >
          <DailyAnalyticsPanel />
        </Suspense>
      </section>
    </div>
  );
}

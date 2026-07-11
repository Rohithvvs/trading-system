import { lazy, Suspense } from "react";
import { ChartSkeleton, PanelSkeleton } from "../../components/Skeleton";

const PaperTradingPage = lazy(() =>
  import("../../components/PaperTradingPage").then((m) => ({ default: m.PaperTradingPage })),
);

export function PaperTradingRoutePage() {
  return (
    <div className="dashboard-grid retail-page">
      <Suspense
        fallback={
          <PanelSkeleton title="Loading paper trading">
            <ChartSkeleton height={160} />
          </PanelSkeleton>
        }
      >
        <PaperTradingPage />
      </Suspense>
    </div>
  );
}

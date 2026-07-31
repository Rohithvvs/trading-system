import { MarketOverviewWidget } from "../components/widgets/MarketOverviewWidget";
import { TodaysScanWidget } from "../components/widgets/TodaysScanWidget";
import { RecommendationSummaryWidget } from "../components/widgets/RecommendationSummaryWidget";
import { PortfolioSummaryWidget } from "../components/widgets/PortfolioSummaryWidget";
import { RecentActivityWidget } from "../components/widgets/RecentActivityWidget";
import { MarketStatusWidget } from "../components/widgets/MarketStatusWidget";
import { ResearchStatusWidget } from "../components/widgets/ResearchStatusWidget";
import { QuickActionsWidget } from "../components/widgets/QuickActionsWidget";
import { ScannerStatusWidget } from "../components/widgets/ScannerStatusWidget";
import { ErrorBoundary } from "../components/ErrorBoundary";

export function DashboardPage() {
  return (
    <div
      className="dashboard-grid-container"
      data-testid="dashboard-page"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(12, 1fr)",
        gap: "16px",
        padding: "16px",
        maxWidth: "1400px",
        margin: "0 auto",
      }}
    >
      {/* Row 1: Market Overview (4), Today's Scan (4), Recommendations (4) */}
      <div style={{ gridColumn: "span 4" }}>
        <ErrorBoundary fallbackTitle="Market Overview Error">
          <MarketOverviewWidget />
        </ErrorBoundary>
      </div>
      <div style={{ gridColumn: "span 4" }}>
        <ErrorBoundary fallbackTitle="Today's Scan Error">
          <TodaysScanWidget />
        </ErrorBoundary>
      </div>
      <div style={{ gridColumn: "span 4" }}>
        <ErrorBoundary fallbackTitle="Recommendations Error">
          <RecommendationSummaryWidget />
        </ErrorBoundary>
      </div>

      {/* Row 2: Portfolio Summary (6), Recent Activity (6) */}
      <div style={{ gridColumn: "span 6" }}>
        <ErrorBoundary fallbackTitle="Portfolio Summary Error">
          <PortfolioSummaryWidget />
        </ErrorBoundary>
      </div>
      <div style={{ gridColumn: "span 6" }}>
        <ErrorBoundary fallbackTitle="Recent Activity Error">
          <RecentActivityWidget />
        </ErrorBoundary>
      </div>

      {/* Row 3: Market Status (3), Research Status (3), Quick Actions (3), Scanner Status (3) */}
      <div style={{ gridColumn: "span 3" }}>
        <ErrorBoundary fallbackTitle="Market Status Error">
          <MarketStatusWidget />
        </ErrorBoundary>
      </div>
      <div style={{ gridColumn: "span 3" }}>
        <ErrorBoundary fallbackTitle="Research Status Error">
          <ResearchStatusWidget />
        </ErrorBoundary>
      </div>
      <div style={{ gridColumn: "span 3" }}>
        <ErrorBoundary fallbackTitle="Quick Actions Error">
          <QuickActionsWidget />
        </ErrorBoundary>
      </div>
      <div style={{ gridColumn: "span 3" }}>
        <ErrorBoundary fallbackTitle="Scanner Status Error">
          <ScannerStatusWidget />
        </ErrorBoundary>
      </div>
    </div>
  );
}

export default DashboardPage;

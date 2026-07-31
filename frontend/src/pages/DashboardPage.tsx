import { useState } from "react";
import { AppShell } from "../layout/AppShell";
import { MarketRegimeBanner } from "../components/MarketRegimeBanner";
import { ScannerStatusCard } from "../components/ScannerStatusCard";
import { TopRecommendationsWidget, type Recommendation } from "../components/TopRecommendationsWidget";
import { PaperPortfolioSummaryCard } from "../components/PaperPortfolioSummaryCard";
import { OrderDrawer } from "../components/OrderDrawer";

export function DashboardPage() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedRec, setSelectedRec] = useState<Recommendation | undefined>(undefined);

  function handleTradeClick(rec: Recommendation) {
    setSelectedRec(rec);
    setDrawerOpen(true);
  }

  return (
    <AppShell title="Personal AI Trading Research Workstation">
      <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        {/* Top Quadrant: Market Regime Banner */}
        <MarketRegimeBanner />

        {/* 2-Column Quadrant: Recommendations & Scanner Status */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "20px" }}>
          <TopRecommendationsWidget onTradeClick={handleTradeClick} />
          <ScannerStatusCard />
        </div>

        {/* Bottom Quadrant: Paper Portfolio Summary */}
        <PaperPortfolioSummaryCard />
      </div>

      {/* Slide-Out Execution Drawer */}
      <OrderDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initialData={selectedRec}
      />
    </AppShell>
  );
}
export default DashboardPage;

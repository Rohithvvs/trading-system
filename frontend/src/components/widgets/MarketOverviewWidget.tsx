import { WidgetContainer } from "../WidgetContainer";
import { MarketRegimeBanner } from "../MarketRegimeBanner";

export function MarketOverviewWidget() {
  return (
    <WidgetContainer
      id="market-overview"
      title="Market Overview & Regime"
      subtitle="Indian Market Benchmark Indices"
      gridSpan={4}
      testId="widget-market-overview"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <MarketRegimeBanner regime="bullish" score={78} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
          <div style={{ padding: "8px 12px", background: "var(--surface-2)", borderRadius: "6px" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>NIFTY 50</span>
            <div style={{ fontWeight: 600, color: "var(--positive-text)" }}>24,850.40 (+0.65%)</div>
          </div>
          <div style={{ padding: "8px 12px", background: "var(--surface-2)", borderRadius: "6px" }}>
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>BANK NIFTY</span>
            <div style={{ fontWeight: 600, color: "var(--positive-text)" }}>52,310.15 (+0.42%)</div>
          </div>
        </div>
      </div>
    </WidgetContainer>
  );
}

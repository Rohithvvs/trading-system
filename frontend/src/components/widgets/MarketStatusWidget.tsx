import { WidgetContainer } from "../WidgetContainer";
import { SystemHealthBadge } from "../SystemHealthBadge";
import TokenStatus from "../TokenStatus";

export function MarketStatusWidget() {
  return (
    <WidgetContainer
      id="market-status"
      title="Market Status & Token Health"
      subtitle="Fyers API Session State"
      gridSpan={3}
      testId="widget-market-status"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Market Status:</span>
          <SystemHealthBadge status="online" text="OPEN" />
        </div>
        <TokenStatus />
      </div>
    </WidgetContainer>
  );
}

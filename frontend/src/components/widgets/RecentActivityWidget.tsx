import { WidgetContainer } from "../WidgetContainer";

export function RecentActivityWidget() {
  return (
    <WidgetContainer
      id="recent-activity"
      title="Recent Activity Timeline"
      subtitle="Latest System & Trade Events"
      gridSpan={6}
      testId="widget-recent-activity"
    >
      <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: "0.85rem", color: "var(--text-secondary)" }}>
        <li style={{ padding: "8px 0", borderBottom: "1px solid var(--border-subtle, rgba(255,255,255,0.05))" }}>
          <span style={{ color: "var(--text-muted)", marginRight: "8px" }}>10:15 AM</span>
          Executed paper order <strong style={{ color: "var(--text)" }}>BUY INFY (150 Qty)</strong>
        </li>
        <li style={{ padding: "8px 0", borderBottom: "1px solid var(--border-subtle, rgba(255,255,255,0.05))" }}>
          <span style={{ color: "var(--text-muted)", marginRight: "8px" }}>09:45 AM</span>
          Opportunity Scanner finished daily run (12 candidates found)
        </li>
        <li style={{ padding: "8px 0" }}>
          <span style={{ color: "var(--text-muted)", marginRight: "8px" }}>09:15 AM</span>
          Market opened (NIFTY50 Regime: Bullish)
        </li>
      </ul>
    </WidgetContainer>
  );
}

import { WidgetContainer } from "../WidgetContainer";
import { Link } from "react-router-dom";

export function TodaysScanWidget() {
  return (
    <WidgetContainer
      id="todays-scan"
      title="Today's Opportunity Scan"
      subtitle="NIFTY 500 Screening Candidates"
      gridSpan={4}
      action={
        <Link to="/research/scanner" style={{ fontSize: "0.8rem", color: "var(--accent)", textDecoration: "none" }}>
          View All →
        </Link>
      }
      testId="widget-todays-scan"
    >
      <div style={{ display: "flex", justifyContent: "space-around", textAlign: "center", padding: "12px 0" }}>
        <div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--positive-text)" }}>12</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>BUY Signals</div>
        </div>
        <div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--warning)" }}>18</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>WATCH Signals</div>
        </div>
        <div>
          <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-muted)" }}>470</div>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>REJECTED</div>
        </div>
      </div>
    </WidgetContainer>
  );
}

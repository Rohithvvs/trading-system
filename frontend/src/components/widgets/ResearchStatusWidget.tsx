import { WidgetContainer } from "../WidgetContainer";

export function ResearchStatusWidget() {
  return (
    <WidgetContainer
      id="research-status"
      title="Research Pipeline Status"
      subtitle="Candle Store & Idea Sync"
      gridSpan={3}
      testId="widget-research-status"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "8px", fontSize: "0.85rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "var(--text-muted)" }}>Candle Store Sync:</span>
          <span style={{ color: "var(--positive-text)", fontWeight: 500 }}>UP TO DATE</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "var(--text-muted)" }}>Active Research Ideas:</span>
          <span style={{ color: "var(--text)", fontWeight: 600 }}>5 Active</span>
        </div>
      </div>
    </WidgetContainer>
  );
}

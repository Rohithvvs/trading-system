import { WidgetContainer } from "../WidgetContainer";
import { ScannerProgress } from "../ScannerProgress";

export function ScannerStatusWidget() {
  return (
    <WidgetContainer
      id="scanner-status"
      title="Scanner Status & Fanout Health"
      subtitle="Execution Engine Metrics"
      gridSpan={3}
      testId="widget-scanner-status"
    >
      <ScannerProgress data={{ stage: "IDLE", progress: 100 }} error={null} startTime={null} />
    </WidgetContainer>
  );
}

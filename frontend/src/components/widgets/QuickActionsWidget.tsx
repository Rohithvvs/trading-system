import { WidgetContainer } from "../WidgetContainer";
import { QuickActionsBar } from "../QuickActionsBar";

export function QuickActionsWidget() {
  return (
    <WidgetContainer
      id="quick-actions"
      title="Quick Actions"
      subtitle="Shortcuts & Execution"
      gridSpan={3}
      testId="widget-quick-actions"
    >
      <QuickActionsBar />
    </WidgetContainer>
  );
}

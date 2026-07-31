import { WidgetContainer } from "../WidgetContainer";
import { PaperPortfolioSummaryCard } from "../PaperPortfolioSummaryCard";

export function PortfolioSummaryWidget() {
  return (
    <WidgetContainer
      id="portfolio-summary"
      title="Paper Portfolio Summary"
      subtitle="Capital Allocation & PnL"
      gridSpan={6}
      testId="widget-portfolio-summary"
    >
      <PaperPortfolioSummaryCard />
    </WidgetContainer>
  );
}

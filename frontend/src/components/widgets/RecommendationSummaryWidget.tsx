import { WidgetContainer } from "../WidgetContainer";
import { TopRecommendationsWidget } from "../TopRecommendationsWidget";

export function RecommendationSummaryWidget() {
  return (
    <WidgetContainer
      id="recommendation-summary"
      title="AI Top Recommendations"
      subtitle="Highest Confidence Setups"
      gridSpan={4}
      testId="widget-recommendation-summary"
    >
      <TopRecommendationsWidget items={[]} />
    </WidgetContainer>
  );
}

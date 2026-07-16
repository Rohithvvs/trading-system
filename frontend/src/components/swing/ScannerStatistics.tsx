import { memo } from "react";
import { Card, CardHeader } from "../../design-system";
import { SummaryRow } from "../SummaryRow";

export type ScannerStatMetric = {
  label: string;
  value: string | number;
  helper: string;
  tone?: "default" | "positive" | "warning" | "negative";
};

export type ScannerStatisticsProps = {
  metrics: ScannerStatMetric[];
};

/**
 * Scanner KPI statistics section — reuses SummaryRow inside Markets card layout.
 */
export const ScannerStatistics = memo(function ScannerStatistics({ metrics }: ScannerStatisticsProps) {
  if (!metrics?.length) return null;

  return (
    <Card className="swing-statistics" aria-label="Scanner statistics">
      <CardHeader label="Statistics" title="Scanner statistics" description="Latest scan funnel and recommendation counts." />
      <SummaryRow metrics={metrics} />
    </Card>
  );
});

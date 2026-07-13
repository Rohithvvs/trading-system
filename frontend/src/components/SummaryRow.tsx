import { StatCard } from "../design-system/components/StatCard";

type SummaryMetric = {
  label: string;
  value: string | number;
  helper: string;
  tone?: "default" | "positive" | "warning" | "negative";
};

type SummaryRowProps = {
  metrics: SummaryMetric[];
};

/**
 * KPI strip — large numbers, short labels, reduced helper noise.
 */
export function SummaryRow({ metrics }: SummaryRowProps) {
  return (
    <section className="summary-row summary-row--kpi" aria-label="Scan summary">
      {metrics.map((metric) => (
        <StatCard
          key={metric.label}
          label={metric.label}
          value={metric.value}
          subtitle={shortHelper(metric.helper)}
          tone={metric.tone ?? "default"}
          compact
        />
      ))}
    </section>
  );
}

/** Keep only first short phrase for cleaner KPI cards */
function shortHelper(helper: string): string {
  if (!helper) return "";
  const cut = helper.split(/[.,]/)[0];
  return cut.length > 42 ? `${cut.slice(0, 40)}…` : cut;
}

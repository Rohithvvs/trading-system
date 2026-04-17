type SummaryMetric = {
  label: string;
  value: string | number;
  helper: string;
  tone?: "default" | "positive" | "warning" | "negative";
};

type SummaryRowProps = {
  metrics: SummaryMetric[];
};

export function SummaryRow({ metrics }: SummaryRowProps) {
  return (
    <section className="summary-row" aria-label="Scan summary">
      {metrics.map((metric) => (
        <article key={metric.label} className={`metric-card metric-card-${metric.tone ?? "default"}`}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          <p>{metric.helper}</p>
        </article>
      ))}
    </section>
  );
}

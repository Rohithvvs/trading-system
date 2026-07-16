import type { ReactNode } from "react";

type Props = {
  label: string;
  value: ReactNode;
  subtitle?: string;
  tone?: "default" | "positive" | "warning" | "negative" | "info";
  icon?: ReactNode;
  trend?: ReactNode;
  helper?: string;
  className?: string;
  compact?: boolean;
};

/** KPI / metric card — large number, small label, optional trend */
export function StatCard({
  label,
  value,
  subtitle,
  tone = "default",
  icon,
  trend,
  helper,
  className = "",
  compact,
}: Props) {
  return (
    <article
      className={[
        "ds-stat",
        `ds-stat--${tone}`,
        compact ? "ds-stat--compact" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="ds-stat__top">
        <span className="ds-stat__label">{label}</span>
        {icon ? (
          <span className="ds-stat__icon" aria-hidden>
            {icon}
          </span>
        ) : null}
      </div>
      <div className="ds-stat__value">{value}</div>
      {(subtitle || trend) && (
        <div className="ds-stat__meta">
          {trend ? <span className="ds-stat__trend">{trend}</span> : null}
          {subtitle ? <span className="ds-stat__subtitle">{subtitle}</span> : null}
        </div>
      )}
      {helper ? <p className="ds-stat__helper">{helper}</p> : null}
    </article>
  );
}

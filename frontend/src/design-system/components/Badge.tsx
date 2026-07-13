import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "positive" | "negative" | "warning" | "info" | "buy" | "sell" | "watch";

type Props = {
  children: ReactNode;
  tone?: BadgeTone;
  icon?: ReactNode;
  className?: string;
  title?: string;
};

export function Badge({ children, tone = "neutral", icon, className = "", title }: Props) {
  return (
    <span className={`ds-badge ds-badge--${tone} ${className}`.trim()} title={title}>
      {icon ? <span className="ds-badge__icon" aria-hidden>{icon}</span> : null}
      <span>{children}</span>
    </span>
  );
}

export function StatusPill({
  status,
  label,
  className = "",
}: {
  status: "online" | "offline" | "degraded" | "idle";
  label: string;
  className?: string;
}) {
  return (
    <span className={`ds-status-pill ds-status-pill--${status} ${className}`.trim()}>
      <span className="ds-status-pill__dot" aria-hidden />
      <span>{label}</span>
    </span>
  );
}

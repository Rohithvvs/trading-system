import type { ReactNode } from "react";
import { Button, type ButtonVariant } from "./Button";

type Action = {
  label: string;
  onClick: () => void;
  variant?: ButtonVariant;
};

type Props = {
  title: string;
  description: string;
  icon?: ReactNode;
  primaryAction?: Action;
  secondaryAction?: Action;
  className?: string;
};

/** Illustration-style empty states with one clear primary action */
export function EmptyState({
  title,
  description,
  icon,
  primaryAction,
  secondaryAction,
  className = "",
}: Props) {
  return (
    <div className={`ds-empty ${className}`.trim()} role="status">
      <div className="ds-empty__illustration" aria-hidden>
        {icon ?? <DefaultEmptyIcon />}
      </div>
      <h3 className="ds-empty__title">{title}</h3>
      <p className="ds-empty__desc">{description}</p>
      {(primaryAction || secondaryAction) && (
        <div className="ds-empty__actions">
          {primaryAction ? (
            <Button
              variant={primaryAction.variant ?? "trade"}
              onClick={primaryAction.onClick}
            >
              {primaryAction.label}
            </Button>
          ) : null}
          {secondaryAction ? (
            <Button
              variant={secondaryAction.variant ?? "ghost"}
              onClick={secondaryAction.onClick}
            >
              {secondaryAction.label}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}

function DefaultEmptyIcon() {
  return (
    <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
      <rect x="8" y="12" width="48" height="40" rx="8" stroke="currentColor" strokeWidth="2" opacity="0.35" />
      <path d="M16 40 L28 28 L36 34 L48 20" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.55" />
      <circle cx="48" cy="20" r="3" fill="currentColor" opacity="0.55" />
    </svg>
  );
}

import type { ReactNode } from "react";

type Props = {
  label?: string;
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  className?: string;
};

export function SectionHeader({ label, title, subtitle, icon, actions, className = "" }: Props) {
  return (
    <div className={`ds-section-header ${className}`.trim()}>
      <div className="ds-section-header__text">
        {(label || icon) && (
          <div className="ds-section-header__label-row">
            {icon ? <span className="ds-section-header__icon" aria-hidden>{icon}</span> : null}
            {label ? <p className="ds-label">{label}</p> : null}
          </div>
        )}
        <h2 className="ds-section-header__title">{title}</h2>
        {subtitle ? <p className="ds-muted ds-section-header__sub">{subtitle}</p> : null}
      </div>
      {actions ? <div className="ds-section-header__actions">{actions}</div> : null}
    </div>
  );
}

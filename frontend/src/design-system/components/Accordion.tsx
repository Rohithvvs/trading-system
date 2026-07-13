import { useId, useState, type ReactNode } from "react";

type Props = {
  title: string;
  subtitle?: string;
  icon?: ReactNode;
  tooltip?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
};

export function Accordion({
  title,
  subtitle,
  icon,
  tooltip,
  defaultOpen = true,
  children,
  className = "",
  actions,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  const btnId = useId();

  return (
    <div className={`ds-accordion ${open ? "is-open" : ""} ${className}`.trim()}>
      <div className="ds-accordion__header">
        <button
          type="button"
          id={btnId}
          className="ds-accordion__trigger"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
        >
          {icon ? <span className="ds-accordion__icon" aria-hidden>{icon}</span> : null}
          <span className="ds-accordion__titles">
            <span className="ds-accordion__title">
              {title}
              {tooltip}
            </span>
            {subtitle ? <span className="ds-accordion__sub">{subtitle}</span> : null}
          </span>
          <span className="ds-accordion__chevron" aria-hidden>
            {open ? "▾" : "▸"}
          </span>
        </button>
        {actions ? <div className="ds-accordion__actions">{actions}</div> : null}
      </div>
      {open ? (
        <div id={panelId} role="region" aria-labelledby={btnId} className="ds-accordion__body">
          {children}
        </div>
      ) : null}
    </div>
  );
}

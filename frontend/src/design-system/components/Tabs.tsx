import type { ReactNode } from "react";

export type TabItem = {
  id: string;
  label: string;
  badge?: string | number;
  disabled?: boolean;
};

type Props = {
  items: TabItem[];
  value: string;
  onChange: (id: string) => void;
  ariaLabel?: string;
  className?: string;
  /** underline | pill | segment */
  variant?: "underline" | "pill" | "segment";
};

export function Tabs({
  items,
  value,
  onChange,
  ariaLabel = "Sections",
  className = "",
  variant = "underline",
}: Props) {
  return (
    <div
      className={`ds-tabs ds-tabs--${variant} ${className}`.trim()}
      role="tablist"
      aria-label={ariaLabel}
    >
      {items.map((item) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={selected}
            id={`tab-${item.id}`}
            data-testid={`tab-${item.id}`}
            disabled={item.disabled}
            className={`ds-tab ${selected ? "is-active" : ""}`}
            onClick={() => onChange(item.id)}
          >
            <span>{item.label}</span>
            {item.badge != null && item.badge !== "" ? (
              <span className="ds-tab__badge">{item.badge}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  id,
  activeId,
  children,
  className = "",
}: {
  id: string;
  activeId: string;
  children: ReactNode;
  className?: string;
}) {
  if (id !== activeId) return null;
  return (
    <div
      role="tabpanel"
      id={`panel-${id}`}
      aria-labelledby={`tab-${id}`}
      className={className}
    >
      {children}
    </div>
  );
}

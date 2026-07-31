import type { ReactNode } from "react";

interface WidgetContainerProps {
  id?: string;
  title: string;
  subtitle?: string;
  gridSpan?: 3 | 4 | 6 | 12;
  action?: ReactNode;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  children: ReactNode;
  testId?: string;
}

export function WidgetContainer({
  id,
  title,
  subtitle,
  gridSpan = 4,
  action,
  isLoading = false,
  error = null,
  onRetry,
  children,
  testId,
}: WidgetContainerProps) {
  const spanClass = `grid-span-${gridSpan}`;

  return (
    <section
      id={id}
      className={`ds-card widget-container ${spanClass}`}
      data-testid={testId || `widget-${title.toLowerCase().replace(/\s+/g, "-")}`}
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        padding: "16px",
        borderRadius: "var(--radius-lg, 12px)",
        background: "var(--surface, #141a22)",
        border: "1px solid var(--border, #2a3444)",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "12px",
          paddingBottom: "8px",
          borderBottom: "1px solid var(--border, #2a3444)",
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600, color: "var(--text, #f0f4f8)" }}>
            {title}
          </h3>
          {subtitle && (
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted, #8b9aab)" }}>
              {subtitle}
            </span>
          )}
        </div>
        {action && <div>{action}</div>}
      </header>

      <div style={{ flex: 1, position: "relative" }}>
        {isLoading ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "120px",
              color: "var(--text-muted)",
              fontSize: "0.875rem",
            }}
            aria-busy="true"
          >
            <div className="ds-skeleton" style={{ width: "100%", height: "100px", borderRadius: "8px" }} />
          </div>
        ) : error ? (
          <div
            style={{
              padding: "12px",
              borderRadius: "8px",
              background: "var(--negative-soft, rgba(239, 68, 68, 0.1))",
              border: "1px solid var(--negative, #ef4444)",
              color: "var(--negative-text, #f87171)",
              fontSize: "0.875rem",
            }}
          >
            <p style={{ margin: "0 0 8px 0", fontWeight: 500 }}>Unable to load widget data</p>
            <p style={{ margin: 0, fontSize: "0.75rem", opacity: 0.85 }}>{error}</p>
            {onRetry && (
              <button
                type="button"
                className="ds-btn ds-btn--sm"
                onClick={onRetry}
                style={{ marginTop: "8px" }}
              >
                Retry
              </button>
            )}
          </div>
        ) : (
          children
        )}
      </div>
    </section>
  );
}

/**
 * Professional skeleton loaders — replace bare "Loading..." text.
 * Uses existing CSS shimmer (.profile-skel / .app-skel).
 */

import type { CSSProperties, ReactNode } from "react";

type SkelProps = {
  height?: number | string;
  width?: number | string;
  className?: string;
  style?: CSSProperties;
  rounded?: number | string;
};

export function Skeleton({ height = 16, width = "100%", className = "", style, rounded = 8 }: SkelProps) {
  return (
    <div
      className={`app-skel ${className}`}
      style={{
        height,
        width,
        borderRadius: rounded,
        ...style,
      }}
      aria-hidden
    />
  );
}

export function MetricCardSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="app-skel-metrics" style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="metric-card app-skel" style={{ minWidth: 140, minHeight: 72, flex: "1 1 140px" }} />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="table-scroll" aria-busy="true" aria-label="Loading table">
      <table className="candidate-table">
        <thead>
          <tr>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i}>
                <Skeleton height={12} width="70%" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => (
                <td key={c}>
                  <Skeleton height={14} width={c === 0 ? "60%" : "80%"} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ChartSkeleton({ height = 220 }: { height?: number }) {
  return <div className="app-skel chart-skel" style={{ height, width: "100%", borderRadius: 12 }} aria-hidden />;
}

export function PanelSkeleton({ title, children }: { title?: string; children?: ReactNode }) {
  return (
    <section className="panel" aria-busy="true">
      {title ? (
        <div className="panel-header" style={{ marginBottom: 12 }}>
          <div>
            <Skeleton height={10} width={80} style={{ marginBottom: 8 }} />
            <Skeleton height={20} width={160} />
          </div>
        </div>
      ) : null}
      {children ?? (
        <>
          <MetricCardSkeleton count={3} />
          <div style={{ marginTop: 16 }}>
            <TableSkeleton rows={4} cols={4} />
          </div>
        </>
      )}
    </section>
  );
}

export function AvatarSkeleton({ size = 48 }: { size?: number }) {
  return <Skeleton height={size} width={size} rounded="50%" className="avatar-skel" />;
}

export function ListSkeleton({ items = 4 }: { items?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {Array.from({ length: items }).map((_, i) => (
        <Skeleton key={i} height={48} rounded={10} />
      ))}
    </div>
  );
}

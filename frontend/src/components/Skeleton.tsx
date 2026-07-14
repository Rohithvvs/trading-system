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
      className={`skeleton ${className}`}
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

export function TextSkeleton({ lines = 3, short = false }: { lines?: number; short?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={`skeleton ${short && i === lines - 1 ? "skeleton--text-short" : "skeleton--text"}`} />
      ))}
    </div>
  );
}

export function MetricCardSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", width: "100%" }}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="skeleton skeleton--card"
          style={{ minWidth: 140, height: 80, flex: "1 1 140px" }}
        />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="skeleton skeleton--row" style={r === 0 ? { opacity: 0.5, height: 36 } : undefined} />
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 220 }: { height?: number }) {
  return <div className="skeleton skeleton--chart" style={{ height }} aria-hidden />;
}

export function PanelSkeleton({ title, children }: { title?: string; children?: ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }} aria-busy="true">
      {title ? (
        <div>
          <div className="skeleton skeleton--heading" />
        </div>
      ) : null}
      {children ?? (
        <>
          <MetricCardSkeleton count={3} />
          <ChartSkeleton height={100} />
          <TableSkeleton rows={4} cols={4} />
        </>
      )}
    </div>
  );
}

export function CardSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="skeleton-grid">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton skeleton--card" style={{ height: 140 }} />
      ))}
    </div>
  );
}

export function ListSkeleton({ items = 4 }: { items?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="skeleton" style={{ height: 48, borderRadius: 8 }} />
      ))}
    </div>
  );
}

export function ScannerSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%" }}>
      <div className="skeleton skeleton--row" style={{ height: 48 }} />
      <div style={{ display: "flex", gap: 10 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 72, width: 150, borderRadius: 12, flex: "1 1 150px" }} />
        ))}
      </div>
      <TableSkeleton rows={5} cols={6} />
    </div>
  );
}

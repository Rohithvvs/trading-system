import type { ChangeEvent, ReactNode } from "react";

import type { ThemeMode } from "../types";

type DashboardHeaderProps = {
  isLoading: boolean;
  lastScanAt: string | null;
  marketStatus: string;
  search: string;
  onSearchChange: (value: string) => void;
  onRunScanner: () => void;
  topN: number;
  lookback: number;
  timeframe: string;
  onTopNChange: (value: number) => void;
  onLookbackChange: (value: number) => void;
  onTimeframeChange: (value: string) => void;
  theme: ThemeMode;
  onThemeToggle: () => void;
};

export function DashboardHeader({
  isLoading,
  lastScanAt,
  marketStatus,
  search,
  onSearchChange,
  onRunScanner,
  topN,
  lookback,
  timeframe,
  onTopNChange,
  onLookbackChange,
  onTimeframeChange,
  theme,
  onThemeToggle,
}: DashboardHeaderProps) {
  return (
    <header className="dashboard-header panel">
      <div className="header-brand">
        <div>
          <p className="section-label">Nifty 500 swing workstation</p>
          <h1>Swing Decision Dashboard</h1>
        </div>
        <div className="header-meta">
          <StatusPill label="Market" value={marketStatus} tone={marketStatus === "Open" ? "positive" : "neutral"} />
          <StatusPill
            label="Last scan"
            value={lastScanAt ? new Date(lastScanAt).toLocaleString() : "Not run yet"}
            tone="neutral"
          />
        </div>
      </div>

      <div className="header-actions">
        <label className="search-input" aria-label="Quick search">
          <span>Quick search</span>
          <input
            type="search"
            value={search}
            placeholder="Search symbol"
            onChange={(event: ChangeEvent<HTMLInputElement>) => onSearchChange(event.target.value)}
          />
        </label>

        <div className="scan-controls" aria-label="Scanner settings">
          <InlineField label="Timeframe">
            <select value={timeframe} onChange={(event) => onTimeframeChange(event.target.value)}>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </InlineField>
          <InlineField label="Lookback">
            <input
              type="number"
              min={60}
              max={365}
              value={lookback}
              onChange={(event) => onLookbackChange(Number(event.target.value))}
            />
          </InlineField>
          <InlineField label="Top set">
            <input
              type="number"
              min={5}
              max={50}
              value={topN}
              onChange={(event) => onTopNChange(Number(event.target.value))}
            />
          </InlineField>
        </div>

        <div className="header-buttons">
          <button type="button" className="button ghost-button" onClick={onThemeToggle}>
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
          <button type="button" className="button primary-button" onClick={onRunScanner} disabled={isLoading}>
            {isLoading ? "Scanning..." : "Run Nifty 500 Swing Scanner"}
          </button>
        </div>
      </div>
    </header>
  );
}

function InlineField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="inline-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function StatusPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "positive" | "neutral";
}) {
  return (
    <div className={`status-pill status-pill-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

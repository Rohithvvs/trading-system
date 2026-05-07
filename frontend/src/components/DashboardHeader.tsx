import type { ChangeEvent, ReactNode } from "react";
import { InfoTooltip } from './InfoTooltip';
import { TOOLTIPS } from '../constants/tooltips';

import type { ThemeMode } from "../types";
import NotificationBell from "./NotificationBell";

type DashboardHeaderProps = {
  isLoading: boolean;
  lastScanAt: string | null;
  lastScanLabel?: string | null;
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
  lastScanLabel,
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
            value={lastScanLabel ?? (lastScanAt ? new Date(lastScanAt).toLocaleString() : "Not run yet")}
            tone="neutral"
          />
        </div>
      </div>

      <div className="header-actions">
        <div className="scan-controls" aria-label="Scanner settings">
          <InlineField label="Timeframe" tooltip={TOOLTIPS.SCANNER.TIMEFRAME}>
            <select value={timeframe} onChange={(event) => onTimeframeChange(event.target.value)}>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
              <option value="1d">1d</option>
            </select>
          </InlineField>
          <InlineField label="Lookback" tooltip={TOOLTIPS.SCANNER.LOOKBACK}>
            <input
              type="number"
              min={60}
              max={365}
              placeholder="180"
              value={lookback}
              onChange={(event) => onLookbackChange(Number(event.target.value))}
            />
          </InlineField>
          <InlineField label="Top set" tooltip={TOOLTIPS.SCANNER.TOP_SET}>
            <input
              type="number"
              min={5}
              max={50}
              placeholder="20"
              value={topN}
              onChange={(event) => onTopNChange(Number(event.target.value))}
            />
          </InlineField>
        </div>

        <div className="header-buttons">
          <NotificationBell />
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

function InlineField({ label, children, tooltip }: { label: string; children: ReactNode; tooltip?: string }) {
  return (
    <label className="inline-field">
      <span>
        {label}
        {tooltip ? <InfoTooltip content={tooltip} /> : null}
      </span>
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

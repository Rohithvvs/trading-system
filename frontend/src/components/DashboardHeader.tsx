import type { ChangeEvent, ReactNode } from "react";
import { InfoTooltip } from './InfoTooltip';
import { TOOLTIPS } from '../constants/tooltips';

import type { ThemeMode } from "../types";
import NotificationBell from "./NotificationBell";

function formatScanTime(isoString: string | null): string {
  if (!isoString) return "No scan has been completed yet";
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return "No scan has been completed yet";

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);

  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? '' : 's'} ago`;
  
  const day = date.getDate().toString().padStart(2, '0');
  const month = date.toLocaleString('en-US', { month: 'short' });
  const year = date.getFullYear();
  let hour = date.getHours();
  const minute = date.getMinutes().toString().padStart(2, '0');
  const ampm = hour >= 12 ? 'PM' : 'AM';
  hour = hour % 12;
  if (hour === 0) hour = 12;
  const hourStr = hour.toString().padStart(2, '0');
  
  return `${day} ${month} ${year}, ${hourStr}:${minute} ${ampm}`;
}


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
  universe: string;
  universes: { name: string; count: number }[];
  onTopNChange: (value: number) => void;
  onLookbackChange: (value: number) => void;
  onTimeframeChange: (value: string) => void;
  onUniverseChange: (value: string) => void;
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
  universe,
  universes,
  onTopNChange,
  onLookbackChange,
  onTimeframeChange,
  onUniverseChange,
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
            label="Last Scan Completed"
            value={formatScanTime(lastScanAt)}
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
          <InlineField label="Universe">
            <select value={universe} onChange={(event) => onUniverseChange(event.target.value)}>
              {universes.map((item) => (
                <option key={item.name} value={item.name}>{item.name} ({item.count})</option>
              ))}
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
          <button data-testid="run-scanner-button" type="button" className="button primary-button" onClick={onRunScanner} disabled={isLoading}>
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

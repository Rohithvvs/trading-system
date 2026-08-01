import { memo, type ChangeEvent, type ReactNode } from "react";
import { useAuth } from '../hooks/useAuth';
import type { ThemeMode } from "../types";
import NotificationBell from "./NotificationBell";

function formatScanTime(isoString: string | null): string {
  if (!isoString) return "No scan yet";
  const date = new Date(isoString);
  if (isNaN(date.getTime())) return "No scan yet";

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60000);

  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

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

export const DashboardHeader = memo(function DashboardHeader({
  isLoading,
  lastScanAt,
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
  const { user, logout } = useAuth();

  return (
    <header className="dashboard-header">
      {/* Row 1: Title + Market Status + Last Scan */}
      <div className="dh-row dh-row--top">
        <div className="dh-title-group">
          <p className="dh-sublabel">Nifty 500 swing workstation</p>
          <h1 className="dh-title">Swing Decision Dashboard</h1>
        </div>
        <div className="dh-meta-group">
          <span className="dh-scan-time">
            Last Scan: <strong>{formatScanTime(lastScanAt)}</strong>
          </span>
        </div>
      </div>

      {/* Row 2: Controls + Buttons */}
      <div className="dh-row dh-row--bottom">
        <div className="dh-controls">
          <InlineField label="Timeframe">
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
          <InlineField label="Lookback">
            <input
              type="number"
              min={60}
              max={365}
              placeholder="180"
              value={lookback}
              onChange={(event) => onLookbackChange(Number(event.target.value))}
            />
          </InlineField>
          <InlineField label="Top set">
            <input
              type="number"
              min={5}
              max={50}
              placeholder="20"
              value={topN}
              onChange={(event) => onTopNChange(Number(event.target.value))}
            />
          </InlineField>
          <div className="dh-search">
            <label className="dh-search-label">
              <span className="sr-only">Search ticker</span>
              <input
                type="search"
                placeholder="Search ticker…"
                value={search}
                onChange={(event) => onSearchChange(event.target.value)}
                aria-label="Search ticker"
                className="dh-search-input"
              />
            </label>
          </div>
          <div className="dh-actions">
            <NotificationBell />
            <button type="button" className="dh-btn dh-btn--ghost" onClick={onThemeToggle} aria-label="Toggle theme">
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            {user && (
              <button type="button" className="dh-btn dh-btn--ghost" onClick={logout}>
                Sign Out
              </button>
            )}
            <button
              data-testid="run-scanner-button"
              type="button"
              className="dh-btn dh-btn--primary"
              onClick={onRunScanner}
              disabled={isLoading}
            >
              {isLoading ? "Scanning…" : "Run Scanner"}
            </button>
          </div>
        </div>
      </div>
    </header>
  );
});

function InlineField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="dh-field">
      <span className="dh-field-label">{label}</span>
      {children}
    </label>
  );
}

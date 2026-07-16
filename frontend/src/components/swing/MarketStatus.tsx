import { memo } from "react";

function formatScanTime(isoString: string | null | undefined): string {
  if (!isoString) return "No scan yet";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "No scan yet";

  const now = new Date();
  const diffMinutes = Math.floor((now.getTime() - date.getTime()) / 60000);

  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

  const day = date.getDate().toString().padStart(2, "0");
  const month = date.toLocaleString("en-US", { month: "short" });
  const year = date.getFullYear();
  let hour = date.getHours();
  const minute = date.getMinutes().toString().padStart(2, "0");
  const ampm = hour >= 12 ? "PM" : "AM";
  hour = hour % 12;
  if (hour === 0) hour = 12;

  return `${day} ${month} ${year}, ${hour.toString().padStart(2, "0")}:${minute} ${ampm}`;
}

export type MarketStatusProps = {
  marketStatus: string;
  isLoading?: boolean;
  hasScanResult?: boolean;
  lastScanAt?: string | null;
  universe?: string;
  timeframe?: string;
  scannedSymbols?: number | null;
};

/**
 * Compact market / scan status strip for the Swing Decision Dashboard.
 * Uses Markets page status-pill styling — not a standalone page header.
 */
export const MarketStatus = memo(function MarketStatus({
  marketStatus,
  isLoading = false,
  hasScanResult = false,
  lastScanAt = null,
  universe = "NIFTY500",
  timeframe = "1d",
  scannedSymbols = null,
}: MarketStatusProps) {
  const marketOpen = marketStatus === "Open";

  return (
    <div className="scanner-status-bar swing-market-status" aria-label="Market status">
      <span className={`ds-status-pill ds-status-pill--${marketOpen ? "online" : "offline"}`}>
        <span className="ds-status-pill__dot" aria-hidden />
        Market {marketOpen ? "open" : "closed"}
      </span>
      <span className={`ds-status-pill ds-status-pill--${isLoading ? "online" : hasScanResult ? "online" : "idle"}`}>
        <span className="ds-status-pill__dot" aria-hidden />
        {isLoading ? "Scanning…" : hasScanResult ? "Scan ready" : "Awaiting scan"}
      </span>
      <span className="ds-caption scanner-status-bar__meta">
        {universe} · {timeframe}
        {scannedSymbols != null ? ` · ${scannedSymbols} scanned` : ""}
        {" · "}
        Last scan: <strong>{formatScanTime(lastScanAt)}</strong>
      </span>
    </div>
  );
});

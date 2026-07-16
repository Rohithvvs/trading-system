import { memo, useEffect, useMemo, useState } from "react";
import { isMarketOpenForDisplay } from "../utils/tradingHours";

function formatScanTime(isoString: string | null | undefined): string | null {
  if (!isoString) return null;
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return null;
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

function formatDuration(seconds: number | null): string | null {
  if (seconds == null || seconds < 0) return null;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

type LastScanCardProps = {
  lastScanAt: string | null | undefined;
  isLoading: boolean;
  scannedSymbols: number | null | undefined;
  durationSec: number | null;
  compact?: boolean;
};

export const MarketStatusCard = memo(function MarketStatusCard({ compact }: { compact?: boolean }) {
  const [marketStatus, setMarketStatus] = useState(() => isMarketOpenForDisplay());

  useEffect(() => {
    const check = () => setMarketStatus(isMarketOpenForDisplay());
    check();
    const id = setInterval(check, 60_000);
    return () => clearInterval(id);
  }, []);

  const isOpen = marketStatus === "Open";

  return (
    <article
      className={`status-card${compact ? " status-card--compact" : ""}`}
      data-status={isOpen ? "open" : "closed"}
      aria-label={`Market is ${isOpen ? "open" : "closed"}`}
      aria-live="polite"
    >
      <span className="status-card__label">Market</span>
      <span className="status-card__value">
        <span className={`status-card__dot${compact ? " status-card__dot--compact" : ""} status-card__dot--${isOpen ? "open" : "closed"}`} aria-hidden />
        {isOpen ? "Open" : "Closed"}
      </span>
    </article>
  );
});

export const LastScanCard = memo(function LastScanCard({
  lastScanAt,
  isLoading,
  scannedSymbols,
  durationSec,
  compact,
}: LastScanCardProps) {
  const formattedTime = useMemo(() => formatScanTime(lastScanAt), [lastScanAt]);
  const duration = useMemo(() => formatDuration(durationSec), [durationSec]);

  const subtitle = useMemo(() => {
    const parts: string[] = [];
    if (duration) parts.push(`Completed in ${duration}`);
    if (scannedSymbols != null) parts.push(`${scannedSymbols} Stocks`);
    return parts.join(" · ") || undefined;
  }, [duration, scannedSymbols]);

  return (
    <article className={`status-card${compact ? " status-card--compact" : ""}`} aria-label="Last scan completed" aria-live="polite">
      <span className="status-card__label">Last Scan Completed</span>
      <span className="status-card__value">
        {isLoading ? "Scanning…" : formattedTime ?? "No scan completed"}
      </span>
      {!compact && subtitle ? <span className="status-card__subtitle">{subtitle}</span> : null}
    </article>
  );
});

export type StatusCardsProps = {
  lastScanAt: string | null | undefined;
  isLoading: boolean;
  scannedSymbols: number | null | undefined;
  durationSec: number | null;
  compact?: boolean;
  className?: string;
};

export const StatusCards = memo(function StatusCards({
  lastScanAt,
  isLoading,
  scannedSymbols,
  durationSec,
  compact,
  className = "",
}: StatusCardsProps) {
  return (
    <section className={`status-cards-row${compact ? " status-cards-row--compact" : ""} ${className}`} aria-label="Scanner status">
      <MarketStatusCard compact={compact} />
      <LastScanCard
        lastScanAt={lastScanAt}
        isLoading={isLoading}
        scannedSymbols={scannedSymbols}
        durationSec={durationSec}
        compact={compact}
      />
    </section>
  );
});

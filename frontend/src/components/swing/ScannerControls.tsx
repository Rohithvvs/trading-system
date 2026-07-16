import { memo, type ReactNode } from "react";
import { Button } from "../../design-system";

export type ScannerControlsProps = {
  isLoading: boolean;
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
};

/**
 * Scanner parameter controls — timeframe, universe, lookback, top set, search, run.
 * Styled as a Markets card body section (no full-page header).
 */
export const ScannerControls = memo(function ScannerControls({
  isLoading,
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
}: ScannerControlsProps) {
  return (
    <div className="swing-controls" aria-label="Scanner controls">
      <div className="swing-controls__grid">
        <ControlField label="Timeframe">
          <select
            value={timeframe}
            onChange={(e) => onTimeframeChange(e.target.value)}
            aria-label="Timeframe"
          >
            <option value="1h">1h</option>
            <option value="4h">4h</option>
            <option value="1d">1d</option>
          </select>
        </ControlField>

        <ControlField label="Universe">
          <select
            value={universe}
            onChange={(e) => onUniverseChange(e.target.value)}
            aria-label="Universe"
          >
            {(universes.length ? universes : [{ name: universe || "NIFTY500", count: 0 }]).map((item) => (
              <option key={item.name} value={item.name}>
                {item.name}
                {item.count ? ` (${item.count})` : ""}
              </option>
            ))}
          </select>
        </ControlField>

        <ControlField label="Lookback">
          <input
            type="number"
            min={60}
            max={365}
            value={lookback}
            onChange={(e) => onLookbackChange(Number(e.target.value))}
            aria-label="Lookback window"
          />
        </ControlField>

        <ControlField label="Top set">
          <input
            type="number"
            min={5}
            max={50}
            value={topN}
            onChange={(e) => onTopNChange(Number(e.target.value))}
            aria-label="Top set size"
          />
        </ControlField>

        <ControlField label="Search" className="swing-controls__search">
          <input
            type="search"
            placeholder="Search ticker…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Search ticker"
          />
        </ControlField>
      </div>

      <div className="swing-controls__actions">
        <Button
          variant="trade"
          data-testid="run-scanner-button"
          onClick={onRunScanner}
          disabled={isLoading}
          loading={isLoading}
        >
          {isLoading ? "Scanning…" : "Run Scanner"}
        </Button>
      </div>
    </div>
  );
});

function ControlField({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`swing-control-field ${className}`.trim()}>
      <span className="swing-control-field__label">{label}</span>
      {children}
    </label>
  );
}

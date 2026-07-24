import { memo } from "react";
import { Card, CardHeader } from "../../design-system";
import { InfrastructureStatus } from "../InfrastructureStatus";
import { ScannerProgress } from "../ScannerProgress";
import { MarketStatus } from "./MarketStatus";
import { ScannerControls } from "./ScannerControls";
import { ScannerStatistics, type ScannerStatMetric } from "./ScannerStatistics";
import { DataFeedNotice } from "./DataFeedNotice";
import { QuickScannerActions } from "./QuickScannerActions";
import type { ScreenerResponse } from "../../types";

export type SwingDecisionDashboardProps = {
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
  screenerResult?: ScreenerResponse | null;
  summaryMetrics?: ScannerStatMetric[];
  scanError?: string | null;
  progressData?: {
    stage: string;
    progress: number;
    current_symbol?: string;
    worker_id?: number;
    done?: number;
    remaining?: number;
    eta_sec?: number;
  } | null;
  scanStartTime?: number | null;
};

/**
 * Complete Swing Decision Dashboard embedded as Markets page sections.
 * Not a standalone page — inherits Markets container width, cards, and spacing.
 */
export const SwingDecisionDashboard = memo(function SwingDecisionDashboard({
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
  screenerResult = null,
  summaryMetrics = [],
  scanError = null,
  progressData = null,
  scanStartTime = null,
}: SwingDecisionDashboardProps) {
  const lastScanAt =
    screenerResult?.last_scan_completed_at ??
    screenerResult?.scanned_at ??
    screenerResult?.analysis?.generated_at ??
    null;

  return (
    <section className="swing-decision-dashboard" aria-label="Swing Decision Dashboard">
      <Card className="swing-decision-dashboard__main">
        <CardHeader
          label="Swing"
          title="Swing Decision Dashboard"
          description="Configure the scanner, check infrastructure, and run a Nifty 500 swing scan."
        />

        <MarketStatus
          isLoading={isLoading}
          hasScanResult={!!screenerResult}
          lastScanAt={lastScanAt}
          universe={universe}
          timeframe={timeframe}
          scannedSymbols={screenerResult?.scanned_symbols ?? null}
        />

        <div className="swing-decision-dashboard__section">
          <h3 className="ds-title swing-section-title">Scanner controls</h3>
          <ScannerControls
            isLoading={isLoading}
            search={search}
            onSearchChange={onSearchChange}
            onRunScanner={onRunScanner}
            topN={topN}
            lookback={lookback}
            timeframe={timeframe}
            universe={universe}
            universes={universes}
            onTopNChange={onTopNChange}
            onLookbackChange={onLookbackChange}
            onTimeframeChange={onTimeframeChange}
            onUniverseChange={onUniverseChange}
          />
        </div>

        {isLoading && progressData ? (
          <div className="swing-decision-dashboard__section">
            <ScannerProgress
              data={progressData}
              error={scanError}
              startTime={scanStartTime}
              onRetry={onRunScanner}
            />
          </div>
        ) : null}

        {scanError && !isLoading ? (
          <div className="panel error-state swing-decision-dashboard__section" role="alert">
            <h3 className="ds-title">Scan failed</h3>
            <p>{scanError}</p>
            <button type="button" className="button primary-button" onClick={onRunScanner} style={{ marginTop: 12 }}>
              Retry scan
            </button>
          </div>
        ) : null}
      </Card>

      <InfrastructureStatus />

      <ScannerStatistics metrics={summaryMetrics} />

      <DataFeedNotice warning={screenerResult?.data_warning} />

      <QuickScannerActions
        hasResults={!!screenerResult}
        isLoading={isLoading}
        favoritesCount={screenerResult?.shortlisted_symbols?.length ?? 0}
        resultsCount={screenerResult?.all_analyzed_stocks?.length ?? screenerResult?.matches?.length ?? 0}
        onRunScanner={onRunScanner}
      />
    </section>
  );
});

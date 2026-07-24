import { AreaChart, Area, ResponsiveContainer, YAxis } from "recharts";
import type { CandidateRow, BacktestEquityPoint } from "../types";
import { InfoTooltip } from "./InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";
import { memo, useMemo, useState, useCallback } from "react";
import { checkCanPlaceBuyOrder } from "../utils/tradingHours";
import { SignalBadge as DsSignalBadge } from "../design-system";
import { useResearchPrefetch } from "../hooks/useResearchPrefetch";

type CandidateTableProps = {
  rows: CandidateRow[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onBuy?: (row: CandidateRow) => void;
  liveTicks?: Record<string, number>;
};

export const CandidateTable = memo(function CandidateTable({ rows, selectedSymbol, onSelect, onBuy, liveTicks }: CandidateTableProps) {
  const { hoverHandlers } = useResearchPrefetch();

  if (!rows.length) {
    return (
      <section className="panel table-panel">
        <div className="ds-empty" role="status" aria-live="polite">
          <h3 className="ds-empty__title">No matching stocks</h3>
          <p className="ds-empty__desc">
            Try relaxing the signal filter, score range, or search term to see more scan results.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel table-panel">
      <div className="panel-header">
        <div>
          <p className="section-label">Favorites</p>
          <h2>Scan results</h2>
        </div>
        <p className="panel-helper">
          <abbr title="Signal comes from the final recommendation layer">Signal</abbr>, score, confidence, trade plan, and support evidence stay aligned in one table.
        </p>
      </div>

      {/* Desktop/tablet table */}
      <div className="table-scroll table-scroll--sticky">
        <table className="candidate-table candidate-table--pro" style={{ width: "100%", borderCollapse: "separate", borderSpacing: 0 }}>
          <thead>
            <tr>
              <th className="col-sticky-left" style={{ minWidth: "3rem" }}>Rank</th>
              <th className="col-sticky-symbol" style={{ minWidth: "6.5rem" }}>Symbol</th>
              <th style={{ minWidth: "6.5rem" }}>Signal</th>
              <th style={{ minWidth: "8rem" }}>Score</th>
              <th style={{ minWidth: "11rem" }}>Trade plan <InfoTooltip content={TOOLTIPS.SCANNER.ENTRY_PRICE} /></th>
              <th style={{ minWidth: "7rem" }}>Curve <InfoTooltip content="Backtested trailing equity curve" /></th>
              <th style={{ minWidth: "5.5rem" }}>Trend</th>
              <th style={{ minWidth: "5rem" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <CandidateTableRow 
                key={row.symbol} 
                row={row} 
                livePrice={liveTicks?.[row.symbol]} 
                isSelected={selectedSymbol === row.symbol}
                onSelect={onSelect}
                onBuy={onBuy}
                prefetchProps={hoverHandlers(row.symbol)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile cards (shown ≤600px) */}
      <div className="candidate-cards">
        {rows.map((row) => (
          <CandidateCard
            key={row.symbol}
            row={row}
            livePrice={liveTicks?.[row.symbol]}
            isSelected={selectedSymbol === row.symbol}
            onSelect={onSelect}
            onBuy={onBuy}
            prefetchProps={hoverHandlers(row.symbol)}
          />
        ))}
      </div>
    </section>
  );
});

const CandidateCard = memo(({
  row,
  livePrice,
  isSelected,
  onSelect,
  onBuy,
  prefetchProps,
}: {
  row: CandidateRow;
  livePrice?: number;
  isSelected: boolean;
  onSelect: (symbol: string) => void;
  onBuy?: (row: CandidateRow) => void;
  prefetchProps?: PrefetchProps;
}) => {
  const distanceToEntry = useMemo(() => {
    if (!livePrice || !row.entryHigh) return null;
    return (((livePrice - row.entryHigh) / row.entryHigh) * 100).toFixed(2);
  }, [livePrice, row.entryHigh]);

  const dynamicRiskReward = useMemo(() => {
    if (!livePrice || !row.stopLoss || !row.target1 || livePrice <= row.stopLoss) return null;
    return ((row.target1 - livePrice) / (livePrice - row.stopLoss)).toFixed(2);
  }, [livePrice, row.stopLoss, row.target1]);

  const backtestData = row.analysisItem?.backtests?.[0];
  const equityCurve: BacktestEquityPoint[] = useMemo(() => {
    const fromBt = backtestData?.equity_curve || [];
    if (fromBt.length > 0) return fromBt;
    // Fallback: price series from OHLCV so cards with full analysis never show empty charts.
    const ohlcv = row.analysisItem?.ohlcv || [];
    if (ohlcv.length === 0) return [];
    return ohlcv.slice(-60).map((c, i) => ({
      label: String(i),
      equity: c.close,
    }));
  }, [backtestData, row.analysisItem?.ohlcv]);
  const regime = row.newsSentiment === "Bullish" || row.newsSentiment === "Bearish" ? "CATALYST" : "STANDARD";

  return (
    <article
      className={`candidate-card ${isSelected ? "is-selected" : ""}`}
      onClick={() => onSelect(row.symbol)}
      tabIndex={0}
      role="button"
      aria-label={`${row.symbol} - ${row.signal} - Score ${row.score === null || row.score === undefined ? "N/A" : row.score.toFixed(1)}`}
      {...prefetchProps}
    >
      {/* Top row: Rank + Symbol + Signal */}
      <div className="candidate-card__top">
        <div className="candidate-card__symbol-area">
          <span className="candidate-card__rank">#{row.rank ?? "--"}</span>
          <div className="candidate-card__symbol-meta">
            <div className="candidate-card__symbol" title={row.symbol}>{row.symbol}</div>
            <div className="candidate-card__volume">{row.volume} Vol</div>
          </div>
        </div>
        <div className="candidate-card__signal">
          <SignalBadge value={row.signal} />
        </div>
      </div>

      {/* Score bar */}
      <div className="candidate-card__score-row">
        <div className="candidate-card__score-bar">
          <div
            className="candidate-card__score-fill"
            style={{
              width: `${Math.min(row.score ?? 0, 100)}%`,
              background: "var(--accent)",
            }}
          />
        </div>
        <div className="candidate-card__score-label">
          <span>Score <strong>{row.score === null || row.score === undefined ? "N/A" : row.score.toFixed(1)}</strong></span>
          <span>Conf <strong>{row.confidence === null || row.confidence === undefined ? "N/A" : `${Math.round(row.confidence * 100)}%`}</strong></span>
        </div>
      </div>

      {/* Info grid */}
      <div className="candidate-card__info-grid">
        <div className="candidate-card__info-item">
          <span className="candidate-card__info-label">Entry</span>
          <span className="candidate-card__info-value">
            {livePrice ? (
              <span>
                {formatNumber(livePrice)}
                <span style={{ fontSize: "0.85em", marginLeft: "3px", color: livePrice > (row.entryHigh ?? Infinity) ? "var(--negative)" : "var(--positive)" }}>
                  ({distanceToEntry}%)
                </span>
              </span>
            ) : (
              formatZone(row.entryLow, row.entryHigh)
            )}
          </span>
        </div>
        <div className="candidate-card__info-item">
          <span className="candidate-card__info-label">SL / TP</span>
          <span className="candidate-card__info-value">{formatNumber(row.stopLoss)} / {formatNumber(row.target1)}</span>
        </div>
        <div className="candidate-card__info-item">
          <span className="candidate-card__info-label">R:R</span>
          <span className="candidate-card__info-value" style={{ color: "var(--accent)" }}>
            {dynamicRiskReward !== null ? dynamicRiskReward : formatNumber(row.riskReward)}x
          </span>
        </div>
        <div className="candidate-card__info-item">
          <span className="candidate-card__info-label">Regime</span>
          <span className="candidate-card__info-value">
            <span style={{
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "4px",
              backgroundColor: regime === "CATALYST" ? "var(--positive)" : "var(--surface-2)",
              color: regime === "CATALYST" ? "#fff" : "var(--text-muted)",
            }}>
              {regime}
            </span>
          </span>
        </div>
      </div>

      {/* Equity curve */}
      <div className="candidate-card__equity">
        {equityCurve.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={equityCurve}>
              <defs>
                <linearGradient id={`colorEq${row.symbol}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--positive)" stopOpacity={0.3}/>
                  <stop offset="95%" stopColor="var(--positive)" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <YAxis domain={['dataMin', 'dataMax']} hide />
              <Area type="monotone" dataKey="equity" stroke="var(--positive)" fillOpacity={1} fill={`url(#colorEq${row.symbol})`} />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>No chart data</span>
        )}
      </div>

      {/* Trend tags */}
      <div className="candidate-card__trend">
        <span className="candidate-card__trend-item">{row.trend}</span>
        <span className="candidate-card__trend-item">{row.momentum}</span>
      </div>

      {/* BUY button */}
      <div className="candidate-card__actions">
        <button
          type="button"
          className="ds-btn ds-btn--buy"
          onClick={(event) => {
            event.stopPropagation();
            onBuy?.(row);
          }}
          disabled={!onBuy || row.signal === "REJECT" || !checkCanPlaceBuyOrder().allowed}
          title={!checkCanPlaceBuyOrder().allowed ? "Market closed — BUY disabled" : "BUY on Paper Desk"}
          aria-label={`Buy ${row.symbol}`}
        >
          BUY
        </button>
      </div>
    </article>
  );
});

type PrefetchProps = {
  onMouseEnter?: () => void;
  onFocus?: () => void;
  onTouchStart?: () => void;
};

const CandidateTableRow = memo(({ 
  row, 
  livePrice, 
  isSelected, 
  onSelect, 
  onBuy,
  prefetchProps,
}: { 
  row: CandidateRow; 
  livePrice?: number; 
  isSelected: boolean; 
  onSelect: (symbol: string) => void; 
  onBuy?: (row: CandidateRow) => void; 
  prefetchProps?: PrefetchProps;
}) => {
  const [expanded, setExpanded] = useState(false);

  const distanceToEntry = useMemo(() => {
    if (!livePrice || !row.entryHigh) return null;
    return (((livePrice - row.entryHigh) / row.entryHigh) * 100).toFixed(2);
  }, [livePrice, row.entryHigh]);

  const dynamicRiskReward = useMemo(() => {
    if (!livePrice || !row.stopLoss || !row.target1 || livePrice <= row.stopLoss) return null;
    return ((row.target1 - livePrice) / (livePrice - row.stopLoss)).toFixed(2);
  }, [livePrice, row.stopLoss, row.target1]);

  const backtestData = row.analysisItem?.backtests?.[0];
  const equityCurve: BacktestEquityPoint[] = useMemo(() => {
    const fromBt = backtestData?.equity_curve || [];
    if (fromBt.length > 0) return fromBt;
    const ohlcv = row.analysisItem?.ohlcv || [];
    if (ohlcv.length === 0) return [];
    return ohlcv.slice(-60).map((c, i) => ({
      label: String(i),
      equity: c.close,
    }));
  }, [backtestData, row.analysisItem?.ohlcv]);

  // Determine Regime
  const regime = row.newsSentiment === "Bullish" || row.newsSentiment === "Bearish" ? "CATALYST" : "STANDARD";

  return (
    <>
      <tr
        className={isSelected ? "is-selected" : ""}
        onClick={() => {
          onSelect(row.symbol);
          setExpanded(!expanded);
        }}
        style={{ cursor: "pointer", borderBottom: "1px solid var(--border-color)" }}
        tabIndex={0}
        {...prefetchProps}
      >
        <td className="col-sticky-left" style={{ textAlign: "center", color: "var(--text-muted)" }}>{row.rank ?? "--"}</td>
        <td className="symbol-cell col-sticky-symbol">
          <strong>{row.symbol}</strong>
          <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
            {row.volume} Vol
          </div>
        </td>
        <td>
          <SignalBadge value={row.signal} />
          <div style={{ marginTop: "6px" }}>
            <span style={{ 
              fontSize: "10px", 
              fontWeight: 700, 
              padding: "2px 6px", 
              borderRadius: "4px", 
              backgroundColor: regime === "CATALYST" ? "var(--signal-bullish)" : "var(--bg-surface-elevated)",
              color: regime === "CATALYST" ? "#fff" : "var(--text-secondary)",
              letterSpacing: "0.5px"
            }}>
              {regime}
            </span>
          </div>
        </td>
        <td>
          <div style={{ marginBottom: "6px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "2px" }}>
              <span>Score</span>
              <strong>{row.score === null || row.score === undefined ? "N/A" : row.score.toFixed(1)}</strong>
            </div>
            <div style={{ width: "100%", height: "4px", background: "var(--bg-surface-elevated)", borderRadius: "2px", overflow: "hidden" }}>
              <div style={{ width: `${Math.min(row.score ?? 0, 100)}%`, height: "100%", background: "var(--accent-primary)" }}></div>
            </div>
          </div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "2px", color: "var(--text-secondary)" }}>
              <span>Conviction</span>
              <strong>{row.confidence === null || row.confidence === undefined ? "N/A" : `${Math.round(row.confidence * 100)}%`}</strong>
            </div>
            <div style={{ width: "100%", height: "4px", background: "var(--bg-surface-elevated)", borderRadius: "2px", overflow: "hidden" }}>
              <div style={{ width: `${Math.min((row.confidence || 0) * 100, 100)}%`, height: "100%", background: "var(--text-muted)" }}></div>
            </div>
          </div>
        </td>
        <td style={{ fontSize: "13px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-muted)" }}>Entry:</span>
              <strong>
                {livePrice ? (
                  <span>
                    {formatNumber(livePrice)}
                    <span style={{ fontSize: '0.85em', marginLeft: "4px", color: livePrice > (row.entryHigh ?? Infinity) ? 'var(--signal-bearish)' : 'var(--signal-bullish)' }}>
                      ({distanceToEntry}%)
                    </span>
                  </span>
                ) : (
                  formatZone(row.entryLow, row.entryHigh)
                )}
              </strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-muted)" }}>SL / TP:</span>
              <span style={{ fontWeight: 500 }}>{formatNumber(row.stopLoss)} <span style={{ color: "var(--border-color)" }}>|</span> {formatNumber(row.target1)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "var(--text-muted)" }}>R:R:</span>
              <span style={{ color: "var(--accent-primary)", fontWeight: 600 }}>{dynamicRiskReward !== null ? dynamicRiskReward : formatNumber(row.riskReward)}x</span>
            </div>
          </div>
        </td>
        <td>
          <div style={{ width: "120px", height: "40px" }}>
            {equityCurve.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityCurve}>
                  <defs>
                    <linearGradient id={`colorEquity${row.symbol}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--signal-bullish)" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="var(--signal-bullish)" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <YAxis domain={['dataMin', 'dataMax']} hide />
                  <Area type="monotone" dataKey="equity" stroke="var(--signal-bullish)" fillOpacity={1} fill={`url(#colorEquity${row.symbol})`} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>No chart data</span>
            )}
          </div>
        </td>
        <td style={{ fontSize: "12px" }}>
          <div>{row.trend}</div>
          <div style={{ color: "var(--text-muted)", marginTop: "2px" }}>{row.momentum}</div>
        </td>
        <td>
          <button
            type="button"
            className="ds-btn ds-btn--buy ds-btn--sm"
            onClick={(event) => {
              event.stopPropagation();
              onBuy?.(row);
            }}
            disabled={!onBuy || row.signal === "REJECT" || !checkCanPlaceBuyOrder().allowed}
            title={!checkCanPlaceBuyOrder().allowed ? "Market closed — BUY disabled" : "BUY on Paper Desk"}
            aria-label={`Buy ${row.symbol}`}
          >
            BUY
          </button>
        </td>
      </tr>
    </>
  );
});

function SignalBadge({ value }: { value: CandidateRow["signal"] }) {
  return <DsSignalBadge signal={value} />;
}

function formatNumber(value: number | null) {
  return value === null ? "--" : value.toFixed(2);
}

function formatZone(low: number | null, high: number | null) {
  if (low === null || high === null) {
    return "--";
  }
  return `${low.toFixed(2)} - ${high.toFixed(2)}`;
}

import { AreaChart, Area, ResponsiveContainer, YAxis } from "recharts";
import type { CandidateRow, BacktestEquityPoint } from "../types";
import { InfoTooltip } from "./InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";
import { memo, useMemo, useState } from "react";
import { checkCanPlaceBuyOrder } from "../utils/tradingHours";
import { SignalBadge as DsSignalBadge } from "../design-system";

type CandidateTableProps = {
  rows: CandidateRow[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
  onBuy?: (row: CandidateRow) => void;
  liveTicks?: Record<string, number>;
};

export const CandidateTable = memo(function CandidateTable({ rows, selectedSymbol, onSelect, onBuy, liveTicks }: CandidateTableProps) {
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
    <section className="panel table-panel" style={{ overflow: "visible" }}>
      <div className="panel-header">
        <div>
          <p className="section-label">Favorites</p>
          <h2>Scan results</h2>
        </div>
        <p className="panel-helper">
          <abbr title="Signal comes from the final recommendation layer">Signal</abbr>, score, confidence, trade plan, and support evidence stay aligned in one table.
        </p>
      </div>

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
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
});

const CandidateTableRow = memo(({ 
  row, 
  livePrice, 
  isSelected, 
  onSelect, 
  onBuy 
}: { 
  row: CandidateRow; 
  livePrice?: number; 
  isSelected: boolean; 
  onSelect: (symbol: string) => void; 
  onBuy?: (row: CandidateRow) => void; 
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
  const equityCurve: BacktestEquityPoint[] = backtestData?.equity_curve || [];

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
              <strong>{row.score.toFixed(1)}</strong>
            </div>
            <div style={{ width: "100%", height: "4px", background: "var(--bg-surface-elevated)", borderRadius: "2px", overflow: "hidden" }}>
              <div style={{ width: `${Math.min(row.score, 100)}%`, height: "100%", background: "var(--accent-primary)" }}></div>
            </div>
          </div>
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "2px", color: "var(--text-secondary)" }}>
              <span>Conviction</span>
              <strong>{row.confidence === null ? "--" : `${Math.round(row.confidence * 100)}%`}</strong>
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

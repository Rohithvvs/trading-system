import type { CandidateRow } from "../types";
import { InfoTooltip } from "./InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";

type CandidateTableProps = {
  rows: CandidateRow[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
};

export function CandidateTable({ rows, selectedSymbol, onSelect }: CandidateTableProps) {
  if (!rows.length) {
    return (
      <section className="panel table-panel">
        <div
          className="empty-state"
          aria-live="polite"
          style={{ textAlign: "center", color: "#6b7280", padding: "48px 16px" }}
        >
          <p style={{ margin: 0, fontWeight: 600 }}>No stocks match the current filters.</p>
          <span style={{ display: "block", marginTop: 8 }}>Try relaxing the signal filter, score range, or search term.</span>
        </div>
      </section>
    );
  }

  return (
    <section className="panel table-panel">
      <div className="panel-header">
        <div>
          <p className="section-label">Shortlisted stocks</p>
          <h2>Candidate decision table</h2>
        </div>
        <p className="panel-helper">
          <abbr title="Signal comes from the final recommendation layer">Signal</abbr>, score, confidence, trade plan, and support evidence stay aligned in one table.
        </p>
      </div>

      <div className="table-scroll">
        <table className="candidate-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Symbol</th>
              <th>Signal</th>
              <th>Score</th>
              <th>
                <abbr title="Confidence is the model's conviction after combining technicals, news, and backtest support.">Confidence</abbr>
              </th>
              <th>
                Entry <InfoTooltip content={TOOLTIPS.SCANNER.ENTRY_PRICE} />
              </th>
              <th>
                Stop loss <InfoTooltip content={TOOLTIPS.SCANNER.STOP_LOSS} />
              </th>
              <th>
                Target 1 <InfoTooltip content={TOOLTIPS.SCANNER.TARGET_1} />
              </th>
              <th>
                Target 2 <InfoTooltip content={TOOLTIPS.SCANNER.TARGET_2} />
              </th>
              <th>
                Risk / Reward <InfoTooltip content={TOOLTIPS.SCANNER.RISK_REWARD} />
              </th>
              <th>
                Trend <InfoTooltip content={TOOLTIPS.SCANNER.TREND} />
              </th>
              <th>
                Momentum <InfoTooltip content={TOOLTIPS.SCANNER.MOMENTUM} />
              </th>
              <th>
                Volume <InfoTooltip content={TOOLTIPS.SCANNER.VOLUME} />
              </th>
              <th>
                News <InfoTooltip content={TOOLTIPS.SCANNER.NEWS} />
              </th>
              <th>Last updated</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.symbol}
                className={selectedSymbol === row.symbol ? "is-selected" : ""}
                onClick={() => onSelect(row.symbol)}
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(row.symbol);
                  }
                }}
              >
                <td>{row.rank ?? "--"}</td>
                <td className="symbol-cell">
                  <strong>{row.symbol}</strong>
                </td>
                <td>
                  <SignalBadge value={row.signal} />
                </td>
                <td className="number-cell">{row.score.toFixed(1)}</td>
                <td className="number-cell">{row.confidence === null ? "--" : `${Math.round(row.confidence * 100)}%`}</td>
                <td className="number-cell">{formatZone(row.entryLow, row.entryHigh)}</td>
                <td className="number-cell">{formatNumber(row.stopLoss)}</td>
                <td className="number-cell">{formatNumber(row.target1)}</td>
                <td className="number-cell">{formatNumber(row.target2)}</td>
                <td className="number-cell">{formatNumber(row.riskReward)}</td>
                <td>{row.trend}</td>
                <td>{row.momentum}</td>
                <td>{row.volume}</td>
                <td>{row.newsSentiment}</td>
                <td>{row.lastUpdated ? new Date(row.lastUpdated).toLocaleString() : "--"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="candidate-cards">
        {rows.map((row) => (
          <button
            key={row.symbol}
            type="button"
            className={`candidate-card ${selectedSymbol === row.symbol ? "is-selected" : ""}`}
            onClick={() => onSelect(row.symbol)}
          >
            <div className="candidate-card-top">
              <div>
                <span className="candidate-rank">#{row.rank ?? "--"}</span>
                <h3>{row.symbol}</h3>
              </div>
              <SignalBadge value={row.signal} />
            </div>
            <div className="candidate-card-grid">
              <Metric label="Score" value={row.score.toFixed(1)} />
              <Metric label="Confidence" value={row.confidence === null ? "--" : `${Math.round(row.confidence * 100)}%`} />
              <Metric label="Entry" value={formatZone(row.entryLow, row.entryHigh)} />
              <Metric label="Risk / Reward" value={formatNumber(row.riskReward)} />
              <Metric label="Trend" value={row.trend} />
              <Metric label="News" value={row.newsSentiment} />
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

function SignalBadge({ value }: { value: CandidateRow["signal"] }) {
  return <span className={`signal-badge signal-${value.toLowerCase()}`}>{value}</span>;
}

function Metric({ label, value }: { label: string; value: string }) {
  const tooltipMap: Record<string, string | undefined> = {
    Score: TOOLTIPS.SCANNER.SCORE_MIN,
    Confidence: TOOLTIPS.SCANNER.CONFIDENCE_CHECKBOX,
    Entry: TOOLTIPS.SCANNER.ENTRY_PRICE,
    'Risk / Reward': TOOLTIPS.SCANNER.RISK_REWARD,
    Trend: TOOLTIPS.SCANNER.TREND,
    News: TOOLTIPS.SCANNER.NEWS,
  };

  const tip = tooltipMap[label];

  return (
    <div className="mini-metric">
      <span>
        {label}
        {tip ? <InfoTooltip content={tip} /> : null}
      </span>
      <strong>{value}</strong>
    </div>
  );
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

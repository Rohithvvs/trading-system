import type { ScreenerConditionResult } from "../types";
import { InfoTooltip } from "./InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";

type AllAnalyzedStocksTableProps = {
  stocks: ScreenerConditionResult[];
};

function getRejectionReasons(conditions: Record<string, boolean>, matched: boolean): string[] {
  if (matched) {
    return ["Passed all checks"];
  }

  const reasons: string[] = [];

  if (conditions.data_source_failed) reasons.push("No live data available");
  if (conditions.data_quality_failed) reasons.push("Insufficient historical data");
  if (!conditions.broad_trend_eligibility) reasons.push("Failed broad trend check");
  if (!conditions.hard_filters_pass) reasons.push("Failed hard filters");
  if (!conditions.core_trend_filter_pass) reasons.push("Trend filter failed");
  if (!conditions.core_momentum_filter_pass) reasons.push("Momentum filter failed");
  if (!conditions.basic_liquidity_filter_pass) reasons.push("Liquidity filter failed");

  return reasons.length > 0 ? reasons : ["Failed final threshold"];
}

export function AllAnalyzedStocksTable({ stocks }: AllAnalyzedStocksTableProps) {
  if (!stocks.length) {
    return (
      <section className="panel empty-state">
        <h2>No stocks analyzed</h2>
        <p>Run the scanner to see all analyzed stocks here.</p>
      </section>
    );
  }

  const matched = stocks.filter((s) => s.matched);
  const rejected = stocks.filter((s) => !s.matched);
  const dataIssueCount = stocks.filter((s) => s.conditions?.data_source_failed || s.conditions?.data_quality_failed).length;

  return (
    <section className="panel table-panel">
      <div className="panel-header">
        <div>
          <p className="section-label">Complete Analysis</p>
          <h2>All {stocks.length} analyzed stocks</h2>
        </div>
        <p className="panel-helper">
          {matched.length} passed, {rejected.length} rejected
        </p>
      </div>

      {dataIssueCount > 0 ? (
        <div className="data-issue-banner" role="status" aria-live="polite">
          <strong>⚠ {dataIssueCount} stocks were skipped due to missing or low-quality data.</strong>
          <div style={{ marginTop: 6 }}>Check your FYERS connection or increase the lookback window.</div>
        </div>
      ) : null}

      <div className="table-scroll">
        <table className="candidate-table debug-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Close</th>
              <th>
                Score <InfoTooltip content={TOOLTIPS.SCANNER.SCORE_MIN} />
              </th>
              <th>Tech Signal</th>
              <th>Status</th>
              <th>EMA-20</th>
              <th>SMA-50</th>
              <th>SMA-200</th>
              <th>
                Volume <InfoTooltip content={TOOLTIPS.SCANNER.VOLUME} />
              </th>
              <th>Rejection Reason</th>
            </tr>
          </thead>
          <tbody>
            {matched.map((stock) => (
              <tr key={stock.symbol} className="row-passed">
                <td className="symbol-cell">
                  <strong>{stock.symbol}</strong>
                </td>
                <td className="number-cell">{stock.close > 0 ? stock.close.toFixed(2) : "N/A"}</td>
                <td className="number-cell">{stock.screener_score.toFixed(1)}</td>
                <td>{stock.technical_signal}</td>
                <td>
                  <span className="badge badge-success">Passed</span>
                </td>
                <td className="number-cell">{stock.ema_20 > 0 ? stock.ema_20.toFixed(2) : "N/A"}</td>
                <td className="number-cell">{stock.sma_50 > 0 ? stock.sma_50.toFixed(2) : "N/A"}</td>
                <td className="number-cell">{stock.sma_200 > 0 ? stock.sma_200.toFixed(2) : "N/A"}</td>
                <td className="number-cell">{stock.volume > 0 ? (stock.volume / 1000000).toFixed(1) : "N/A"}M</td>
                <td>
                  <span className="badge badge-success">Passed all checks</span>
                </td>
              </tr>
            ))}
            {rejected.map((stock) => {
              const reasons = getRejectionReasons(stock.conditions, stock.matched);
              const isDataIssue = stock.conditions.data_source_failed || stock.conditions.data_quality_failed;
              return (
                <tr key={stock.symbol} className={`row-rejected ${isDataIssue ? "row-data-issue" : ""}`}>
                  <td className="symbol-cell">
                    <strong>{stock.symbol}</strong>
                  </td>
                  <td className="number-cell">{stock.close > 0 ? stock.close.toFixed(2) : "N/A"}</td>
                  <td className="number-cell">{stock.screener_score.toFixed(1)}</td>
                  <td>{stock.technical_signal}</td>
                  <td>
                    <span className={`badge ${isDataIssue ? "badge-warning" : "badge-danger"}`}>
                      {isDataIssue ? "Warning" : "Failed"}
                    </span>
                  </td>
                  <td className="number-cell">{stock.ema_20 > 0 ? stock.ema_20.toFixed(2) : "N/A"}</td>
                  <td className="number-cell">{stock.sma_50 > 0 ? stock.sma_50.toFixed(2) : "N/A"}</td>
                  <td className="number-cell">{stock.sma_200 > 0 ? stock.sma_200.toFixed(2) : "N/A"}</td>
                  <td className="number-cell">{stock.volume > 0 ? (stock.volume / 1000000).toFixed(1) : "N/A"}M</td>
                  <td>
                    <div className="rejection-reasons">
                      {reasons.map((reason, idx) => (
                        <div key={idx} className="reason-item">
                          {reason}
                        </div>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <style>{`
        .debug-table {
          font-size: 0.85rem;
        }

        .row-passed {
          background-color: rgba(76, 175, 80, 0.05);
        }

        .row-rejected {
          background-color: rgba(244, 67, 54, 0.05);
        }

        .row-data-issue {
          background-color: rgba(255, 193, 7, 0.05);
        }

        .row-rejected:hover {
          background-color: rgba(244, 67, 54, 0.1);
        }

        .badge {
          display: inline-block;
          padding: 0.25rem 0.5rem;
          border-radius: 3px;
          font-size: 0.75rem;
          font-weight: 600;
        }

        .badge-success {
          background-color: #4caf50;
          color: white;
        }

        .badge-danger {
          background-color: #f44336;
          color: white;
        }

        .badge-warning {
          background-color: #ff9800;
          color: white;
        }

        .rejection-reasons {
          font-size: 0.8rem;
          max-width: 200px;
        }

        .reason-item {
          color: #d32f2f;
          padding: 0.25rem 0;
        }
      `}</style>
    </section>
  );
}

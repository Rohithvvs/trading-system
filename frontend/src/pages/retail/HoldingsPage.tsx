import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchHoldings, type HoldingsResponse } from "../../api_retail";
import { apiUrl } from "../../config";

export function HoldingsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<HoldingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchHoldings()
      .then(setData)
      .catch((e: Error) => setError(e.message));
    const id = setInterval(() => {
      void fetchHoldings().then(setData).catch(() => undefined);
    }, 10000);
    return () => clearInterval(id);
  }, []);

  function exportCsv() {
    window.open(apiUrl("/holdings/export"), "_blank");
  }

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Holdings</p>
            <h2>Portfolio holdings</h2>
          </div>
          <button type="button" className="button ghost-button" onClick={exportCsv}>Export CSV</button>
        </div>
        {error ? <div className="warning-box">{error}</div> : null}
        <div className="summary-metrics-row">
          <Metric label="Current value" value={data?.total_current_value} />
          <Metric label="Invested" value={data?.total_invested} />
          <Metric label="PnL" value={data?.total_pnl} pct={data?.total_pnl_pct} signed />
          <Metric label="Today's PnL" value={data?.todays_pnl} signed />
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th>Avg</th>
                <th>LTP</th>
                <th>Invested</th>
                <th>Value</th>
                <th>PnL</th>
                <th>PnL %</th>
                <th>Day PnL</th>
                <th>Sector</th>
              </tr>
            </thead>
            <tbody>
              {(data?.holdings || []).map((h) => (
                <tr key={h.symbol} onClick={() => navigate(`/chart/${h.symbol}`)} style={{ cursor: "pointer" }}>
                  <td><strong>{h.symbol}</strong></td>
                  <td>{h.qty}</td>
                  <td>{h.avg_price.toFixed(2)}</td>
                  <td>{h.ltp.toFixed(2)}</td>
                  <td>₹{h.invested.toLocaleString("en-IN")}</td>
                  <td>₹{h.current_value.toLocaleString("en-IN")}</td>
                  <td className={h.pnl >= 0 ? "pos" : "neg"}>₹{h.pnl.toFixed(2)}</td>
                  <td className={h.pnl_pct >= 0 ? "pos" : "neg"}>{h.pnl_pct.toFixed(2)}%</td>
                  <td className={h.day_pnl >= 0 ? "pos" : "neg"}>₹{h.day_pnl.toFixed(2)}</td>
                  <td>{h.sector || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data?.holdings.length ? <div className="empty-state"><p>No holdings yet. Place CNC buys to build holdings.</p></div> : null}
        </div>
        <div className="two-col" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
          <div>
            <h3>Allocation</h3>
            {(data?.allocation || []).map((a) => (
              <div key={a.symbol} className="ot-preview-row">
                <span>{a.symbol}</span>
                <strong>{a.pct}%</strong>
              </div>
            ))}
          </div>
          <div>
            <h3>Sector exposure</h3>
            {(data?.sector_exposure || []).map((s) => (
              <div key={s.sector} className="ot-preview-row">
                <span>{s.sector}</span>
                <strong>{s.pct}%</strong>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value, pct, signed }: { label: string; value?: number; pct?: number; signed?: boolean }) {
  const v = value ?? 0;
  const cls = signed ? (v >= 0 ? "pos" : "neg") : "";
  return (
    <div className="metric-card">
      <div className="muted-copy">{label}</div>
      <div className={`metric-value ${cls}`}>
        ₹{v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
        {pct != null ? <span className="muted-copy"> ({pct.toFixed(2)}%)</span> : null}
      </div>
    </div>
  );
}

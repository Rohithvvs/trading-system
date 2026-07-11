import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchPositionsView, type PositionRow, type PositionsResponse } from "../../api_retail";
import { closePaperPosition } from "../../api";

type Tab = "open" | "closed" | "intraday" | "carry_forward";

export function PositionsPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<PositionsResponse | null>(null);
  const [tab, setTab] = useState<Tab>("open");
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    void fetchPositionsView()
      .then(setData)
      .catch((e: Error) => setError(e.message));
  };

  useEffect(() => {
    reload();
    const id = setInterval(reload, 8000);
    return () => clearInterval(id);
  }, []);

  const rows: PositionRow[] = data ? data[tab] : [];

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Positions</p>
            <h2>Live MTM · Risk ₹{(data?.total_risk ?? 0).toLocaleString("en-IN")}</h2>
          </div>
          <div className={`metric-value ${(data?.total_mtm ?? 0) >= 0 ? "pos" : "neg"}`}>
            MTM ₹{(data?.total_mtm ?? 0).toLocaleString("en-IN")}
          </div>
        </div>
        <div className="wl-tabs">
          {(["open", "closed", "intraday", "carry_forward"] as Tab[]).map((t) => (
            <button key={t} type="button" className={`wl-tab ${tab === t ? "is-active" : ""}`} onClick={() => setTab(t)}>
              {t.replace("_", " ")} ({data ? data[t].length : 0})
            </button>
          ))}
        </div>
        {error ? <div className="warning-box">{error}</div> : null}
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th>Avg</th>
                <th>LTP</th>
                <th>PnL</th>
                <th>PnL %</th>
                <th>SL</th>
                <th>Target</th>
                <th>R:R</th>
                <th>Type</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={`${p.position_type}-${p.id}`} onClick={() => navigate(`/chart/${p.symbol}`)} style={{ cursor: "pointer" }}>
                  <td><strong>{p.symbol}</strong></td>
                  <td>{p.qty}</td>
                  <td>{p.avg_entry_price.toFixed(2)}</td>
                  <td>{p.current_price.toFixed(2)}</td>
                  <td className={p.unrealized_pnl >= 0 ? "pos" : "neg"}>₹{p.unrealized_pnl.toFixed(2)}</td>
                  <td className={p.unrealized_pnl_pct >= 0 ? "pos" : "neg"}>{p.unrealized_pnl_pct.toFixed(2)}%</td>
                  <td>{p.stop_loss ?? "—"}</td>
                  <td>{p.target ?? "—"}</td>
                  <td>{p.risk_reward ?? "—"}</td>
                  <td>{p.position_type}</td>
                  <td>
                    {tab === "open" ? (
                      <button
                        type="button"
                        className="button ghost-button"
                        onClick={(e) => {
                          e.stopPropagation();
                          void closePaperPosition(p.id).then(reload);
                        }}
                      >
                        Close
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length ? <div className="empty-state"><p>No {tab.replace("_", " ")} positions.</p></div> : null}
        </div>
      </section>
    </div>
  );
}

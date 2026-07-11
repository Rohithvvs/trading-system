import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchHeatmap, type HeatmapResponse } from "../../api_retail";

export function HeatmapPage() {
  const navigate = useNavigate();
  const [groupBy, setGroupBy] = useState("sector");
  const [data, setData] = useState<HeatmapResponse | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchHeatmap(groupBy)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [groupBy]);

  function colorFor(pct: number | null | undefined) {
    if (pct == null) return "var(--surface-3)";
    const intensity = Math.min(Math.abs(pct) / 5, 1);
    if (pct >= 0) return `rgba(56, 178, 109, ${0.15 + intensity * 0.75})`;
    return `rgba(192, 92, 84, ${0.15 + intensity * 0.75})`;
  }

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Market heatmap</p>
            <h2>Interactive sector map</h2>
          </div>
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
            <option value="sector">Sector</option>
            <option value="industry">Industry</option>
            <option value="market_cap">Market Cap</option>
            <option value="index">Index</option>
          </select>
        </div>
        {error ? <div className="warning-box">{error}</div> : null}
        <div className="heatmap-grid">
          {(data?.sectors || []).map((sec) => (
            <button
              key={sec.sector}
              type="button"
              className="heatmap-cell"
              style={{ background: colorFor(sec.change_pct) }}
              onClick={() => setExpanded((e) => (e === sec.sector ? null : sec.sector))}
            >
              <strong>{sec.sector}</strong>
              <div className={((sec.change_pct ?? 0) >= 0) ? "pos" : "neg"}>
                {sec.change_pct != null ? `${sec.change_pct.toFixed(2)}%` : "—"}
              </div>
              <div className="muted-copy">{sec.stock_count} stocks</div>
            </button>
          ))}
        </div>
        {expanded ? (
          <div className="heatmap-expand">
            <h3>{expanded}</h3>
            <div className="heatmap-stocks">
              {(data?.sectors.find((s) => s.sector === expanded)?.stocks || []).map((st) => (
                <button
                  key={st.symbol}
                  type="button"
                  className="heatmap-stock"
                  style={{ background: colorFor(st.change_pct) }}
                  onClick={() => navigate(`/chart/${st.symbol}`)}
                >
                  <strong>{st.symbol}</strong>
                  <span className={((st.change_pct ?? 0) >= 0) ? "pos" : "neg"}>
                    {st.change_pct != null ? `${st.change_pct.toFixed(2)}%` : "—"}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchHoldings, fetchPositionsView, fetchRiskLimits, type HoldingsResponse, type PositionsResponse, type RiskLimits } from "../../api_retail";
import { fetchPaperAccountSummary } from "../../api";

export function PortfolioPage() {
  const [holdings, setHoldings] = useState<HoldingsResponse | null>(null);
  const [positions, setPositions] = useState<PositionsResponse | null>(null);
  const [risk, setRisk] = useState<RiskLimits | null>(null);
  const [account, setAccount] = useState<Record<string, number> | null>(null);

  useEffect(() => {
    void fetchHoldings().then(setHoldings).catch(() => undefined);
    void fetchPositionsView().then(setPositions).catch(() => undefined);
    void fetchRiskLimits().then(setRisk).catch(() => undefined);
    void fetchPaperAccountSummary().then((r) => setAccount(r as unknown as Record<string, number>)).catch(() => undefined);
  }, []);

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Portfolio</p>
            <h2>Unified portfolio view</h2>
          </div>
        </div>
        <div className="summary-metrics-row">
          <Card label="Current value" value={holdings?.total_current_value} />
          <Card label="Invested" value={holdings?.total_invested} />
          <Card label="Total PnL" value={holdings?.total_pnl} signed />
          <Card label="Live MTM" value={positions?.total_mtm} signed />
          <Card label="Available funds" value={account?.available_funds ?? account?.available_cash} />
        </div>
        <div className="quick-links" style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
          <Link className="button primary-button" to="/holdings">Holdings detail</Link>
          <Link className="button ghost-button" to="/positions">Positions</Link>
          <Link className="button ghost-button" to="/orders">Orders</Link>
          <Link className="button ghost-button" to="/settings">Risk settings</Link>
          <Link className="button ghost-button" to="/reports">Reports</Link>
        </div>
        {risk ? (
          <div style={{ marginTop: 16 }}>
            <h3>Risk snapshot</h3>
            <div className="ot-preview-row"><span>Daily PnL</span><strong className={(risk.daily_pnl ?? 0) >= 0 ? "pos" : "neg"}>₹{(risk.daily_pnl ?? 0).toLocaleString("en-IN")}</strong></div>
            <div className="ot-preview-row"><span>Exposure</span><strong>₹{(risk.current_exposure ?? 0).toLocaleString("en-IN")} / ₹{risk.max_exposure.toLocaleString("en-IN")}</strong></div>
            <div className="ot-preview-row"><span>Open positions</span><strong>{risk.open_positions} / {risk.max_open_positions}</strong></div>
            <div className="ot-preview-row"><span>Enforcement</span><strong>{risk.enabled ? "ON (hard reject)" : "OFF"}</strong></div>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function Card({ label, value, signed }: { label: string; value?: number; signed?: boolean }) {
  const v = value ?? 0;
  return (
    <div className="metric-card">
      <div className="muted-copy">{label}</div>
      <div className={`metric-value ${signed ? (v >= 0 ? "pos" : "neg") : ""}`}>
        ₹{v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
      </div>
    </div>
  );
}

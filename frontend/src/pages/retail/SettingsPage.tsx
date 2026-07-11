import { useEffect, useState } from "react";
import { fetchRiskLimits, updateRiskLimits, type RiskLimits } from "../../api_retail";
import { SettingsSessions } from "../SettingsSessions";

export function SettingsPage() {
  const [limits, setLimits] = useState<RiskLimits | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchRiskLimits()
      .then(setLimits)
      .catch((e: Error) => setError(e.message));
  }, []);

  async function save() {
    if (!limits) return;
    try {
      const updated = await updateRiskLimits(limits);
      setLimits({ ...limits, ...updated });
      setMessage("Risk limits saved. Hard enforcement is active on every order.");
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  }

  function field(key: keyof RiskLimits, label: string) {
    if (!limits) return null;
    const val = limits[key];
    if (typeof val === "boolean") {
      return (
        <label className="inline-field" key={key}>
          <span>{label}</span>
          <input
            type="checkbox"
            checked={val}
            onChange={(e) => setLimits({ ...limits, [key]: e.target.checked })}
          />
        </label>
      );
    }
    return (
      <label className="inline-field" key={key}>
        <span>{label}</span>
        <input
          type="number"
          value={Number(val)}
          onChange={(e) => setLimits({ ...limits, [key]: Number(e.target.value) })}
        />
      </label>
    );
  }

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Settings</p>
            <h2>Hard risk limits</h2>
          </div>
          <button type="button" className="button primary-button" onClick={() => void save()}>Save</button>
        </div>
        {error ? <div className="warning-box">{error}</div> : null}
        {message ? <div className="helper-chip">{message}</div> : null}
        {limits ? (
          <>
            <div className="summary-metrics-row" style={{ marginBottom: 16 }}>
              <div className="metric-card">
                <div className="muted-copy">Daily PnL</div>
                <div className={`metric-value ${(limits.daily_pnl ?? 0) >= 0 ? "pos" : "neg"}`}>
                  ₹{(limits.daily_pnl ?? 0).toLocaleString("en-IN")}
                </div>
              </div>
              <div className="metric-card">
                <div className="muted-copy">Exposure</div>
                <div className="metric-value">₹{(limits.current_exposure ?? 0).toLocaleString("en-IN")}</div>
              </div>
              <div className="metric-card">
                <div className="muted-copy">Open positions</div>
                <div className="metric-value">{limits.open_positions ?? 0}</div>
              </div>
            </div>
            <div className="ot-grid">
              {field("enabled", "Enforcement enabled")}
              {field("max_daily_loss", "Max daily loss (₹)")}
              {field("max_trade_loss", "Max trade loss (₹)")}
              {field("max_position_size", "Max position size (₹)")}
              {field("max_exposure", "Max exposure (₹)")}
              {field("max_sector_exposure_pct", "Max sector exposure %")}
              {field("max_leverage", "Max leverage")}
              {field("max_open_positions", "Max open positions")}
            </div>
          </>
        ) : (
          <p className="muted-copy">Loading risk limits…</p>
        )}
      </section>
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Sessions</p>
            <h2>Active devices</h2>
          </div>
        </div>
        <SettingsSessions />
      </section>
    </div>
  );
}

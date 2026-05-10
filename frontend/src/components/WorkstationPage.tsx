import { useEffect, useState } from "react";

import {
  compareScan,
  createWorkstationAlert,
  deleteScannerPreset,
  deleteWorkstationAlert,
  fetchApiHealth,
  fetchMarketOverview,
  fetchRiskSettings,
  fetchSavedScans,
  fetchScanHistory,
  fetchWorkstationAlerts,
  updateRiskSettings,
} from "../api";

type Props = {
  onLoadSavedScan?: (scan: any) => void;
};

export function WorkstationPage({ onLoadSavedScan }: Props) {
  const [market, setMarket] = useState<any | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [savedScans, setSavedScans] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [risk, setRisk] = useState<any | null>(null);
  const [health, setHealth] = useState<any | null>(null);
  const [comparison, setComparison] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [priceAlert, setPriceAlert] = useState({ name: "", symbol: "", condition: ">=", target_price: "" });
  const [scanAlertName, setScanAlertName] = useState("");

  async function load() {
    try {
      const [marketData, historyData, savedData, alertsData, riskData, healthData] = await Promise.all([
        fetchMarketOverview(),
        fetchScanHistory(20),
        fetchSavedScans(),
        fetchWorkstationAlerts(),
        fetchRiskSettings(),
        fetchApiHealth(),
      ]);
      setMarket(marketData);
      setHistory(historyData);
      setSavedScans(savedData);
      setAlerts(alertsData);
      setRisk(riskData);
      setHealth(healthData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workstation.");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCompare(id: number) {
    setComparison(await compareScan(id));
  }

  async function handleCreatePriceAlert() {
    await createWorkstationAlert({
      alert_type: "PRICE",
      name: priceAlert.name || `${priceAlert.symbol} price alert`,
      symbol: priceAlert.symbol,
      condition: priceAlert.condition,
      target_price: Number(priceAlert.target_price),
    });
    setPriceAlert({ name: "", symbol: "", condition: ">=", target_price: "" });
    await load();
  }

  async function handleCreateScanAlert() {
    await createWorkstationAlert({
      alert_type: "SCAN_ENTRY",
      name: scanAlertName || "Scan entry alert",
      scan_name: scanAlertName || "Manual Scan",
    });
    setScanAlertName("");
    await load();
  }

  async function handleSaveRisk() {
    if (!risk) return;
    const next = await updateRiskSettings({
      profile: risk.profile,
      default_position_size_pct: Number(risk.default_position_size_pct),
      max_risk_per_trade_pct: Number(risk.max_risk_per_trade_pct),
    });
    setRisk(next);
  }

  return (
    <main className="dashboard-grid">
      {error ? <section className="panel error-state"><h2>Workstation failed</h2><p>{error}</p></section> : null}

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Home</p>
            <h2>Market Overview</h2>
          </div>
          <button type="button" className="button ghost-button" onClick={() => void load()}>Refresh</button>
        </div>
        <div className="summary-row workstation-summary">
          {(market?.indices ?? []).map((item: any) => <MarketCard key={item.symbol} item={item} />)}
          {market?.vix ? <MarketCard item={market.vix} /> : null}
        </div>
        <div className="workstation-two-col">
          <MoverList title="Top scan scores" rows={market?.top_gainers ?? []} />
          <MoverList title="Lowest scan scores" rows={market?.top_losers ?? []} />
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Saved Scans</p>
            <h2>Reusable scanner presets</h2>
          </div>
        </div>
        <div className="workstation-list">
          {savedScans.length ? savedScans.map((scan) => (
            <article key={scan.id} className="scan-history-item">
              <div>
                <strong>{scan.name}</strong>
                <p className="muted-copy">{scan.universe} | {scan.timeframe} | lookback {scan.lookback_window} | top {scan.top_n}</p>
              </div>
              <div className="meta-inline">
                <button type="button" className="button small-button" onClick={() => onLoadSavedScan?.(scan)}>Load</button>
                <button type="button" className="button ghost-button small-button" onClick={async () => { await deleteScannerPreset(scan.id); await load(); }}>Delete</button>
              </div>
            </article>
          )) : <p className="muted-copy">No saved scans yet. Save one from the scanner tab.</p>}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Scan History</p>
            <h2>Server snapshots</h2>
          </div>
        </div>
        <div className="workstation-list">
          {history.map((item) => (
            <article key={item.id} className="scan-history-item">
              <div>
                <strong>{new Date(item.created_at).toLocaleString()}</strong>
                <p className="muted-copy">{item.shortlisted_count} shortlisted | BUY {item.buy_count} | WATCH {item.watch_count} | {item.data_source ?? "unknown"}</p>
              </div>
              <button type="button" className="button small-button" onClick={() => void handleCompare(item.id)}>Compare</button>
            </article>
          ))}
        </div>
        {comparison ? (
          <div className="subpanel" style={{ marginTop: 12 }}>
            <h3>Comparison</h3>
            <p className="muted-copy">New: {comparison.new_symbols.join(", ") || "--"}</p>
            <p className="muted-copy">Removed: {comparison.removed_symbols.join(", ") || "--"}</p>
            <p className="muted-copy">Stayed: {comparison.stayed_symbols.slice(0, 12).join(", ") || "--"}</p>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Alerts</p><h2>Price and scan-entry alerts</h2></div></div>
        <div className="workstation-two-col">
          <div className="subpanel">
            <h3>Price alert</h3>
            <div className="paper-ticket-grid">
              <input placeholder="Name" value={priceAlert.name} onChange={(e) => setPriceAlert({ ...priceAlert, name: e.target.value })} />
              <input placeholder="Symbol" value={priceAlert.symbol} onChange={(e) => setPriceAlert({ ...priceAlert, symbol: e.target.value.toUpperCase() })} />
              <select value={priceAlert.condition} onChange={(e) => setPriceAlert({ ...priceAlert, condition: e.target.value })}><option value=">=">&gt;=</option><option value="<=">&lt;=</option></select>
              <input type="number" placeholder="Price" value={priceAlert.target_price} onChange={(e) => setPriceAlert({ ...priceAlert, target_price: e.target.value })} />
            </div>
            <button type="button" className="button primary-button" style={{ marginTop: 10 }} onClick={() => void handleCreatePriceAlert()}>Create price alert</button>
          </div>
          <div className="subpanel">
            <h3>Scan-entry alert</h3>
            <input placeholder="Alert name / scan name" value={scanAlertName} onChange={(e) => setScanAlertName(e.target.value)} />
            <button type="button" className="button primary-button" style={{ marginTop: 10 }} onClick={() => void handleCreateScanAlert()}>Create scan alert</button>
          </div>
        </div>
        <div className="workstation-list" style={{ marginTop: 12 }}>
          {alerts.map((alert) => (
            <article key={alert.id} className="scan-history-item">
              <div>
                <strong>{alert.name}</strong>
                <p className="muted-copy">{alert.alert_type} {alert.symbol ?? alert.scan_name ?? ""} | {alert.last_message ?? "Not triggered"}</p>
              </div>
              <button type="button" className="button ghost-button small-button" onClick={async () => { await deleteWorkstationAlert(alert.id); await load(); }}>Delete</button>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Admin</p><h2>Risk and API health</h2></div></div>
        <div className="workstation-two-col">
          <div className="subpanel">
            <h3>Risk profile</h3>
            {risk ? (
              <div className="paper-ticket-grid">
                <select value={risk.profile} onChange={(e) => setRisk({ ...risk, profile: e.target.value })}>
                  <option value="conservative">Conservative</option>
                  <option value="moderate">Moderate</option>
                  <option value="aggressive">Aggressive</option>
                </select>
                <input type="number" value={risk.default_position_size_pct} onChange={(e) => setRisk({ ...risk, default_position_size_pct: Number(e.target.value) })} />
                <input type="number" value={risk.max_risk_per_trade_pct} onChange={(e) => setRisk({ ...risk, max_risk_per_trade_pct: Number(e.target.value) })} />
                <button type="button" className="button primary-button" onClick={() => void handleSaveRisk()}>Save risk</button>
              </div>
            ) : null}
          </div>
          <div className="subpanel">
            <h3>API health</h3>
            <p className="muted-copy">Database size: {health?.database_size_mb ?? "--"} MB</p>
            {(health?.services ?? []).map((item: any) => (
              <p key={item.name} className="muted-copy"><strong>{item.name}</strong>: {item.status} | {item.detail}</p>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}

function MarketCard({ item }: { item: any }) {
  return (
    <article className="metric-card">
      <span>{item.label}</span>
      <strong>{item.price == null ? "--" : item.price.toLocaleString("en-IN")}</strong>
      <p>{item.source}</p>
    </article>
  );
}

function MoverList({ title, rows }: { title: string; rows: any[] }) {
  return (
    <div className="subpanel">
      <h3>{title}</h3>
      {rows.length ? rows.map((row) => (
        <p key={`${title}-${row.symbol}`} className="muted-copy">{row.symbol}: {row.change_pct?.toFixed?.(1) ?? "--"}</p>
      )) : <p className="muted-copy">Run a scan to populate this list.</p>}
    </div>
  );
}

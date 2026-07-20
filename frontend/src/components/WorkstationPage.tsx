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
  getLatestScan,
  getTokenStatus,
} from "../api";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import { isFyersTokenExpired, isFyersTokenUsable } from "../utils/tokenStatus";
import { MetricCardSkeleton } from "./Skeleton";

type Props = {
  onLoadSavedScan?: (scan: any) => void;
  onNavigate?: (view: "scanner" | "paper-trading" | "home") => void;
};

export function WorkstationPage({ onLoadSavedScan, onNavigate }: Props) {
  // Instant shell from cache — never wait on APIs for first paint
  const [market, setMarket] = useState<any | null>(() => getCached(CACHE_KEYS.marketOverview));
  const [savedScans, setSavedScans] = useState<any[]>(() => getCached(CACHE_KEYS.savedScans) || []);
  const [alerts, setAlerts] = useState<any[]>(() => getCached(CACHE_KEYS.workstationAlerts) || []);
  const [risk, setRisk] = useState<any | null>(() => getCached(CACHE_KEYS.riskSettings));
  const [health, setHealth] = useState<any | null>(() => getCached(CACHE_KEYS.apiHealth));
  const [latestScan, setLatestScan] = useState<any | null>(() => getCached(`${CACHE_KEYS.latestScan}:scanner`));
  const [tokenStatus, setTokenStatus] = useState<any | null>(() => getCached(CACHE_KEYS.fyersToken));
  const [error, setError] = useState<string | null>(null);
  const [bootstrapping, setBootstrapping] = useState(
    () => !getCached(CACHE_KEYS.fyersToken) && !getCached(CACHE_KEYS.apiHealth),
  );
  const [priceAlert, setPriceAlert] = useState({ name: "", symbol: "", condition: ">=", target_price: "" });
  const [scanAlertName, setScanAlertName] = useState("");

  async function load() {
    try {
      // Wave 1: critical status (fast, cached) — unblocks banner immediately
      const [tokenData, healthData, latestData] = await Promise.all([
        getTokenStatus().catch(() => null),
        fetchApiHealth().catch(() => null),
        getLatestScan().catch(() => null),
      ]);
      setTokenStatus(tokenData);
      setHealth(healthData);
      setLatestScan(latestData);
      setBootstrapping(false);

      // Wave 2: secondary widgets (parallel, independent)
      const [marketData, savedData, alertsData, riskData] = await Promise.all([
        fetchMarketOverview().catch(() => null),
        fetchSavedScans().catch(() => []),
        fetchWorkstationAlerts().catch(() => []),
        fetchRiskSettings().catch(() => null),
      ]);
      setMarket(marketData);
      setSavedScans(savedData);
      setAlerts(alertsData);
      setRisk(riskData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workstation.");
      setBootstrapping(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

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

  const now = new Date();
  const istTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  const totalMins = istTime.getHours() * 60 + istTime.getMinutes();
  const isEligible = totalMins >= 555 && totalMins <= 1320;

  const isTokenValid = isFyersTokenUsable(tokenStatus);
  const isTokenExpired = isFyersTokenExpired(tokenStatus);
  const tokenStatusKey = String(tokenStatus?.status || "").toLowerCase();
  const isSchedulerRunning = health?.services?.find((s: any) => s.name === "scheduler")?.status === "ok";
  const isDbConnected = health?.services?.find((s: any) => s.name === "database")?.status === "ok";

  let scannerState: "READY" | "PAUSED" | "BLOCKED" = "READY";
  if (!isTokenValid || isTokenExpired) scannerState = "BLOCKED";
  else if (!isEligible) scannerState = "PAUSED";

  let autoScannerState = "🟢 Enabled";
  let autoScannerReason = "";
  if (!isTokenValid || isTokenExpired) {
    autoScannerState = "🔴 Token Expired";
    autoScannerReason =
      tokenStatusKey === "failed" && !tokenStatus?.access_token_active
        ? "Token automation failed. Please update FYERS token."
        : "Please update FYERS token.";
  } else if (!isSchedulerRunning) {
    autoScannerState = "🔴 Scheduler Offline";
    autoScannerReason = "Backend scheduler is down.";
  } else if (!isEligible) {
    autoScannerState = "🟡 Outside Trading Window";
    autoScannerReason = "Window: 09:15 AM - 10:00 PM IST";
  }

  const lastScanDate = latestScan?.last_scan_completed_at ? new Date(latestScan.last_scan_completed_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' }) : "--";
  const nextScanDate = "Mon-Fri, 09:00 AM & 04:00 PM IST";

  const topScore = Math.max(
    ...(latestScan?.buy_candidates?.map((c: any) => c.score) || []),
    ...(latestScan?.watch_candidates?.map((c: any) => c.score) || []),
    0
  );
  
  const lowestScore = Math.min(
    ...(latestScan?.rejected_candidates?.map((c: any) => c.score) || []),
    ...(latestScan?.buy_candidates?.map((c: any) => c.score) || []),
    ...(latestScan?.watch_candidates?.map((c: any) => c.score) || []),
    100
  );

  return (
    <main className="dashboard-grid">
      {error && <section className="panel error-state"><h2>Workstation failed</h2><p>{error}</p></section>}

      {bootstrapping && !tokenStatus && !health ? (
        <section className="panel" aria-busy="true">
          <MetricCardSkeleton count={4} />
        </section>
      ) : null}

      {/* SECTION 1 - SCANNER STATUS BANNER */}
      <section className="panel" style={{ background: scannerState === "READY" ? "rgba(16, 185, 129, 0.1)" : scannerState === "PAUSED" ? "rgba(245, 158, 11, 0.1)" : "rgba(239, 68, 68, 0.1)", borderLeft: `4px solid ${scannerState === "READY" ? "#10b981" : scannerState === "PAUSED" ? "#f59e0b" : "#ef4444"}` }}>
        <div className="panel-header" style={{ marginBottom: 12 }}>
          {scannerState === "READY" && <h2>🟢 Scanner Ready</h2>}
          {scannerState === "PAUSED" && <h2>🟡 Scanner Paused</h2>}
          {scannerState === "BLOCKED" && <h2>🔴 Scanner Blocked</h2>}
        </div>
        <div>
          {scannerState === "READY" && (
            <div className="workstation-two-col">
              <p><strong>Last Scan:</strong> {lastScanDate}</p>
              <p><strong>Next Scheduled Scan:</strong> {nextScanDate}</p>
              <p><strong>FYERS Token:</strong> VALID</p>
              <p><strong>Scheduler:</strong> RUNNING</p>
            </div>
          )}
          {scannerState === "PAUSED" && (
            <div className="workstation-two-col">
              <p><strong>Reason:</strong> Outside Auto-Trigger Window</p>
              <p><strong>Auto Trigger Window:</strong> 09:15 AM – 10:00 PM IST</p>
            </div>
          )}
          {scannerState === "BLOCKED" && (
            <div className="workstation-two-col">
              <p><strong>Reason:</strong> FYERS Token Expired</p>
              <p><strong>Last Successful Scan:</strong> {lastScanDate}</p>
              <p><strong>Action Required:</strong> Generate New Token</p>
            </div>
          )}
        </div>
      </section>

      {/* SECTION 3 - DASHBOARD SUMMARY METRICS */}
      <section className="summary-row workstation-summary" style={{ gap: 16 }}>
        <article className="metric-card">
          <span>Stocks Scanned</span>
          <strong>{latestScan?.total_scanned ?? "--"}</strong>
        </article>
        <article className="metric-card">
          <span>Qualified Stocks</span>
          <strong>{(latestScan?.buy_count || 0) + (latestScan?.watch_count || 0)}</strong>
        </article>
        <article className="metric-card">
          <span>Data Coverage</span>
          <strong>{latestScan ? `${latestScan.valid_symbols} / ${latestScan.total_scanned}` : "--"}</strong>
        </article>
        <article className="metric-card">
          <span>Scan Duration</span>
          <strong>{latestScan?.duration_ms ? `${Math.floor(latestScan.duration_ms / 60000)}m ${Math.floor((latestScan.duration_ms % 60000) / 1000)}s` : "--"}</strong>
        </article>
      </section>

      <div className="workstation-two-col">
        {/* SECTION 2 - AUTOMATION STATUS CARD */}
        <section className="panel">
          <div className="panel-header"><h2>Automation Status</h2></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <p><strong>Auto Scanner Status:</strong> {autoScannerState}</p>
              {autoScannerReason && <p className="muted-copy" style={{ fontSize: "0.85em" }}>{autoScannerReason}</p>}
            </div>
            <p><strong>Scheduler:</strong> {isSchedulerRunning ? "Running" : "Offline"}</p>
            <p><strong>Last Scan:</strong> {lastScanDate}</p>
            <p><strong>Next Scan:</strong> {nextScanDate}</p>
            <p><strong>FYERS Token:</strong> {isTokenValid ? "Valid" : "Expired"}</p>
            <p><strong>Validated:</strong> {tokenStatus?.validated_at ? new Date(tokenStatus.validated_at).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' }) : "--"}</p>
          </div>
        </section>

        {/* SECTION 4 - LATEST SCAN SNAPSHOT */}
        <section className="panel">
          <div className="panel-header"><h2>Latest Scan Snapshot</h2></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <p><strong>Last Run:</strong> {lastScanDate}</p>
            <p><strong>Stocks Scanned:</strong> {latestScan?.total_scanned ?? "--"}</p>
            <p><strong>Qualified:</strong> {(latestScan?.buy_count || 0) + (latestScan?.watch_count || 0)}</p>
            <p><strong>Top Score:</strong> {latestScan ? topScore.toFixed(1) : "--"}</p>
            <p><strong>Lowest Score:</strong> {latestScan && latestScan.total_scanned > 0 ? lowestScore.toFixed(1) : "--"}</p>
          </div>
          <button className="button primary-button" style={{ marginTop: 16 }} onClick={() => onNavigate?.("scanner")}>View Latest Scan</button>
        </section>
      </div>

      <div className="workstation-two-col">
        {/* SECTION 6 - QUICK ACTIONS PANEL */}
        <section className="panel">
          <div className="panel-header"><h2>Quick Actions</h2></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <button className="button primary-button" onClick={() => onNavigate?.("scanner")}>Run Scanner</button>
            <button className="button ghost-button" onClick={() => void load()}>Refresh Market Data</button>
            <button className="button ghost-button" onClick={() => {}}>Generate FYERS Token</button>
            <button className="button ghost-button" onClick={() => onNavigate?.("scanner")}>Open Scanner</button>
            <button className="button ghost-button" onClick={() => window.open("/logs", "_blank")}>Open System Logs</button>
          </div>
        </section>

        {/* SECTION 7 - SYSTEM HEALTH PANEL */}
        <section className="panel">
          <div className="panel-header"><h2>System Health</h2></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <p>{isDbConnected ? "🟢" : "🔴"} Database Connected</p>
            <p>{isTokenValid ? "🟢" : "🔴"} FYERS Connected</p>
            <p>{isSchedulerRunning ? "🟢" : "🔴"} Scheduler Running</p>
            <p>{scannerState === "READY" ? "🟢" : "🟡"} Scanner Ready</p>
            <p>🟢 AI Analysis Available</p>
          </div>
        </section>
      </div>

      {/* SECTION 5 - MARKET OVERVIEW IMPROVEMENTS */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Home</p>
            <h2>Market Overview</h2>
          </div>
          <button type="button" className="button ghost-button" onClick={() => void load()}>Refresh</button>
        </div>
        {!market ? (
          <p className="muted-copy text-center py-4" style={{ textAlign: "center", margin: "20px 0" }}>Loading market data...</p>
        ) : (market.indices?.length === 0 && !market.vix) ? (
          <p className="muted-copy text-center py-4" style={{ textAlign: "center", margin: "20px 0" }}>Market data unavailable</p>
        ) : (
          <div className="summary-row workstation-summary">
            {(market?.indices ?? []).map((item: any) => <MarketCard key={item.symbol} item={item} />)}
            {market?.vix ? <MarketCard item={market.vix} /> : null}
          </div>
        )}
        {market && (market.indices?.length > 0 || market.vix) && (
          <div className="workstation-two-col" style={{ marginTop: 16 }}>
            <MoverList title="Top scan scores" rows={market?.top_gainers ?? []} />
            <MoverList title="Lowest scan scores" rows={market?.top_losers ?? []} />
          </div>
        )}
      </section>

      {/* RETAIN SAVED SCANS */}
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

      {/* RETAIN ALERTS */}
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
      
      {/* RETAIN ADMIN RISK SETTINGS */}
      <section className="panel">
        <div className="panel-header"><div><p className="section-label">Admin</p><h2>Risk Configuration</h2></div></div>
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
      </section>

    </main>
  );
}

function MarketCard({ item }: { item: any }) {
  const source = item.source === "PG_CACHE" || item.source === "REDIS_CACHE" ? "Market Data" : item.source;
  return (
    <article className="metric-card">
      <span>{item.label}</span>
      <strong>{item.price == null ? "--" : item.price.toLocaleString("en-IN")}</strong>
      <p>{source}</p>
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

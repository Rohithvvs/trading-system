import { useEffect, useState } from "react";
import { getTokenHistory, getTokenStatus, saveAccessToken, getLatestScan, TokenStatusResponse } from "../api";

export default function TokenStatus() {
  const [status, setStatus] = useState<TokenStatusResponse | null>(null);
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [refreshInput, setRefreshInput] = useState("");

  async function load() {
    try {
      const res = await getTokenStatus();
      setStatus(res);
      const scanRes = await getLatestScan();
      if (scanRes && scanRes.last_scan_completed_at) {
        setLastScanAt(scanRes.last_scan_completed_at);
      }
    } catch (e: any) {
      // Non-critical background load error
    }
  }

  async function loadHistory() {
    try {
      const res = await getTokenHistory();
      setHistory(res.history || []);
    } catch {
      // History is useful diagnostics, but token status is the critical UI.
    }
  }

  useEffect(() => {
    void load();
    void loadHistory();
    const id = setInterval(() => void load(), 60000);
    return () => clearInterval(id);
  }, []);

  const now = new Date();
  const istTime = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  const totalMins = istTime.getHours() * 60 + istTime.getMinutes();
  const isEligible = totalMins >= 555 && totalMins <= 1320;

  function badge() {
    if (!status || status.status === "no_token") {
      return <span data-testid="token-status-badge" className="badge neutral">No access token</span>;
    }
    if (status.status === "active") {
      return <span data-testid="token-status-badge" className="badge green">Access Token Active</span>;
    }
    if (status.status === "inactive") {
      return <span data-testid="token-status-badge" className="badge yellow">Access Token Inactive</span>;
    }
    return <span data-testid="token-status-badge" className="badge neutral">{status.status}</span>;
  }

  function renderRefreshBanner() {
    if (!status || !status.has_refresh_token) {
      return null;
    }
    
    const days = status.refresh_token_days_remaining;
    if (days === null || days === undefined) return null;
    
    if (days >= 4) {
      return <div className="success-box" style={{ marginBottom: 12 }}>Refresh Token Valid: {days} days remaining</div>;
    } else if (days > 0) {
      return <div className="warning-box" style={{ marginBottom: 12, backgroundColor: '#fff3cd', color: '#856404', padding: '8px', borderRadius: '4px', border: '1px solid #ffeeba' }}>Refresh Token Expiring Soon: {days} days remaining</div>;
    } else {
      return <div className="error-box" style={{ marginBottom: 12 }}>Refresh Token Expired. Please provide a new token.</div>;
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await saveAccessToken(refreshInput.trim());
      await load();
      await loadHistory();
      setSuccessMessage("Refresh token saved. Access token generated automatically.");
      setRefreshInput("");
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel token-management" data-testid="token-management-panel">
      <h3>FYERS Authentication (Refresh Token)</h3>
      <div style={{ marginBottom: 8 }}>{badge()}</div>
      {renderRefreshBanner()}

      <div style={{ marginBottom: 12 }}>
        <div style={{ marginBottom: 8 }}>
          Paste your FYERS Refresh Token here. This token only needs to be entered once for continuous 15-day access.
        </div>
        <strong>Token Info</strong>
        <table className="token-table">
          <tbody>
            <tr>
              <td>Token Status</td>
              <td>{status?.status ?? "no_token"}</td>
            </tr>
            <tr>
              <td>Last Access Token Validation</td>
              <td>{status?.validated_at ? new Date(status.validated_at).toLocaleString() : "-"}</td>
            </tr>
            <tr>
              <td>Auto Renewal Status</td>
              <td>{status?.has_refresh_token ? (status.last_auto_renewal_status || "Pending") : "Not configured"}</td>
            </tr>
            <tr>
              <td>Last Auto Renewal</td>
              <td>{status?.last_auto_renewal_at ? new Date(status.last_auto_renewal_at).toLocaleString() : "-"}</td>
            </tr>
            <tr>
              <td>Last Successful Scan</td>
              <td>{lastScanAt ? new Date(lastScanAt).toLocaleString() : "-"}</td>
            </tr>
            <tr>
              <td>Next Scheduled Scan</td>
              <td>Mon-Fri, 09:00 AM & 04:00 PM IST</td>
            </tr>
            <tr>
              <td>Auto Scan Eligible</td>
              <td>{isEligible ? "YES" : "NO"}</td>
            </tr>
            <tr>
              <td>Auto Scan Window</td>
              <td>09:15–22:00 IST</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style={{ marginBottom: 12 }}>
        <strong>Provide Refresh Token (Access token is generated automatically)</strong>
        
        {error && <div className="error-box" style={{ marginTop: 8 }}>{error}</div>}
        {successMessage && <div className="success-box" style={{ marginTop: 8 }}>{successMessage}</div>}

        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
          <input
            data-testid="refresh-token-input"
            placeholder="Refresh token (Required)"
            type="password"
            value={refreshInput}
            onChange={(e) => setRefreshInput(e.target.value)}
            disabled={saving}
          />
          <button 
            data-testid="save-access-token-button" 
            className="button primary-button" 
            onClick={handleSave} 
            disabled={saving || !refreshInput.trim()}
            style={{ alignSelf: "flex-start" }}
          >
            {saving ? (
              <>
                <span className="spinner"></span>
                Generating Access Token...
              </>
            ) : "Save Token"}
          </button>
        </div>
      </div>

      <div style={{ marginBottom: 12 }}>
        <strong>Token History</strong>
        <table className="token-table">
          <thead>
            <tr><th>Saved At</th><th>Token (masked)</th><th>Status</th><th>Note</th></tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id}>
                <td>{new Date(h.saved_at).toLocaleString()}</td>
                <td>{h.access_token_masked ?? "-"}</td>
                <td>{h.status ?? "-"}</td>
                <td>{h.note ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

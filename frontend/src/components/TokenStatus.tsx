import { useEffect, useState } from "react";
import { getTokenHistory, getTokenStatus, saveAccessToken, getLatestScan } from "../api";

type Status = {
  access_token_active: boolean;
  access_token_saved_at: string | null;
  validated_at?: string | null;
  status: string | null;
  last_error: string | null;
};

export default function TokenStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [accessInput, setAccessInput] = useState("");

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
      return <span data-testid="token-status-badge" className="badge neutral">No token</span>;
    }
    if (status.status === "active") {
      return <span data-testid="token-status-badge" className="badge green">Token Active</span>;
    }
    if (status.status === "inactive") {
      return <span data-testid="token-status-badge" className="badge yellow">Token Inactive</span>;
    }
    return <span data-testid="token-status-badge" className="badge neutral">{status.status}</span>;
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);
    try {
      await saveAccessToken(accessInput.trim());
      await load();
      await loadHistory();
      setSuccessMessage("Token successfully verified and saved.");
      setAccessInput("");
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel token-management" data-testid="token-management-panel">
      <h3>FYERS Access Token</h3>
      <div style={{ marginBottom: 8 }}>{badge()}</div>

      <div style={{ marginBottom: 12 }}>
        <div style={{ marginBottom: 8 }}>
          Paste your manually generated FYERS access token here. This token must be renewed manually when it expires.
        </div>
        <strong>Token Info</strong>
        <table className="token-table">
          <tbody>
            <tr>
              <td>Token Status</td>
              <td>{status?.status ?? "no_token"}</td>
            </tr>
            <tr>
              <td>Last Token Validation</td>
              <td>{status?.validated_at ? new Date(status.validated_at).toLocaleString() : "-"}</td>
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
        <strong>Update access token</strong>
        
        {error && <div className="error-box" style={{ marginTop: 8 }}>{error}</div>}
        {successMessage && <div className="success-box" style={{ marginTop: 8 }}>{successMessage}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <input
            data-testid="access-token-input"
            placeholder="Access token"
            type="password"
            value={accessInput}
            onChange={(e) => setAccessInput(e.target.value)}
            disabled={saving}
          />
          <button 
            data-testid="save-access-token-button" 
            className="button primary-button" 
            onClick={handleSave} 
            disabled={saving || !accessInput.trim()}
          >
            {saving ? (
              <>
                <span className="spinner"></span>
                Validating with broker...
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

import { useEffect, useState } from "react";
import { getTokenHistory, getTokenStatus, saveAccessToken, getLatestScan } from "../api";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import { TableSkeleton } from "./Skeleton";

type Status = {
  access_token_active: boolean;
  access_token_saved_at: string | null;
  validated_at?: string | null;
  status: string | null;
  last_error: string | null;
};

export default function TokenStatus() {
  // Instant paint from cache — token is NOT re-validated against FYERS on every visit
  const [status, setStatus] = useState<Status | null>(() => getCached(CACHE_KEYS.fyersToken));
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);
  const [history, setHistory] = useState<any[]>(() => {
    const h = getCached<{ history?: any[] }>(CACHE_KEYS.fyersTokenHistory);
    return h?.history || [];
  });
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [accessInput, setAccessInput] = useState("");
  const [listLoading, setListLoading] = useState(() => !getCached(CACHE_KEYS.fyersTokenHistory));

  async function load(force = false) {
    try {
      // Parallel: status + scan + history (all cached / deduped)
      const [res, scanRes, hist] = await Promise.all([
        getTokenStatus({ force }),
        getLatestScan().catch(() => null),
        getTokenHistory().catch(() => ({ history: [] })),
      ]);
      setStatus(res);
      if (scanRes && scanRes.last_scan_completed_at) {
        setLastScanAt(scanRes.last_scan_completed_at);
      }
      setHistory(hist?.history || []);
    } catch {
      // Non-critical background load error
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    void load(false);
    // Poll status every 60s using cache (no FYERS round-trip; backend is DB-only)
    const id = setInterval(() => void load(false), 60000);
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
      // Manual reconnect — only path that validates against FYERS
      await saveAccessToken(accessInput.trim());
      await load(true);
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
        {listLoading && history.length === 0 ? (
          <TableSkeleton rows={3} cols={4} />
        ) : (
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
        )}
      </div>
    </section>
  );
}

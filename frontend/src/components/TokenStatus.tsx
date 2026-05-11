import { useEffect, useState } from "react";
import { getTokenHistory, getTokenStatus, saveAccessToken } from "../api";

type Status = {
  access_token_active: boolean;
  access_token_saved_at: string | null;
  status: string | null;
  last_error: string | null;
};

export default function TokenStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [accessInput, setAccessInput] = useState("");

  async function load() {
    try {
      const res = await getTokenStatus();
      setStatus(res);
    } catch (e: any) {
      setError(e.message || String(e));
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
    try {
      await saveAccessToken(accessInput.trim());
      await load();
      await loadHistory();
      alert("Access token saved.");
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
              <td>Last Saved</td>
              <td>{status?.access_token_saved_at ? new Date(status.access_token_saved_at).toLocaleString() : "-"}</td>
            </tr>
            <tr>
              <td>Last Error</td>
              <td>{status?.last_error ?? "-"}</td>
            </tr>
            <tr>
              <td>Status</td>
              <td>{status?.status ?? "no_token"}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style={{ marginBottom: 12 }}>
        <strong>Update access token</strong>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <input
            data-testid="access-token-input"
            placeholder="Access token"
            type="password"
            value={accessInput}
            onChange={(e) => setAccessInput(e.target.value)}
          />
          <button data-testid="save-access-token-button" className="button" onClick={handleSave} disabled={saving || !accessInput.trim()}>
            Save Token
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

      {error ? <div className="error-box">{error}</div> : null}
    </section>
  );
}

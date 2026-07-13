import { useEffect, useState } from "react";
import {
  getTokenHistory,
  getTokenStatus,
  getFyersAuthUrl,
  getLatestScan,
  fetchBrokerToken,
  saveBrokerToken,
  updateBrokerToken,
  deleteBrokerToken,
  validateBrokerToken,
  testBrokerConnection,
} from "../api";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import { TableSkeleton } from "./Skeleton";
import { Badge } from "../design-system/components/Badge";
import { Button } from "../design-system/components/Button";

type Status = {
  access_token_active: boolean;
  access_token_saved_at: string | null;
  validated_at?: string | null;
  expires_at?: string | null;
  expires_in_seconds?: number | null;
  status: string | null;
  last_error: string | null;
  token_masked?: string | null;
};

type BrokerMeta = {
  exists?: boolean;
  broker?: string;
  token_masked?: string | null;
  connection_status?: string;
  has_api_key?: boolean;
  notes?: string | null;
  token_expiry?: string | null;
  last_validated_at?: string | null;
  last_error?: string | null;
};

type HistoryRow = {
  id: number | string;
  saved_at: string;
  broker?: string;
  access_token_masked?: string | null;
  status?: string | null;
  validated?: boolean;
  note?: string | null;
};

const BROKERS: { value: string; label: string }[] = [
  { value: "FYERS", label: "FYERS" },
  { value: "ZERODHA", label: "Zerodha" },
  { value: "UPSTOX", label: "Upstox" },
  { value: "ANGEL", label: "Angel One" },
  { value: "OTHER", label: "Other" },
];

const STATUS_CONFIG: Record<string, { tone: "positive" | "warning" | "negative" | "neutral"; label: string }> = {
  connected: { tone: "positive", label: "Connected" },
  "expiring soon": { tone: "warning", label: "Expiring Soon" },
  expired: { tone: "negative", label: "Expired" },
  invalid: { tone: "negative", label: "Invalid" },
  disconnected: { tone: "neutral", label: "Disconnected" },
};

function normalizeStatus(s: string | null | undefined): string {
  const val = (s || "Disconnected").toLowerCase();
  if (val.includes("connected") && !val.includes("dis")) return "connected";
  if (val.includes("expiring")) return "expiring soon";
  if (val.includes("expired")) return "expired";
  if (val.includes("invalid")) return "invalid";
  return "disconnected";
}

function StatusBadge({ value, testId }: { value: string; testId?: string }) {
  const key = normalizeStatus(value);
  const cfg = STATUS_CONFIG[key] || STATUS_CONFIG.disconnected;
  return (
    <span data-testid={testId || "token-status-badge"}>
      <Badge tone={cfg.tone}>{cfg.label}</Badge>
    </span>
  );
}

function EyeToggle({
  visible,
  onToggle,
  label,
}: {
  visible: boolean;
  onToggle: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      className="token-eye-btn"
      aria-label={visible ? `Hide ${label}` : `Show ${label}`}
      title={visible ? "Hide" : "Show"}
      onClick={onToggle}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        {visible ? (
          <>
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
            <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
            <line x1="1" y1="1" x2="23" y2="23" />
          </>
        ) : (
          <>
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
            <circle cx="12" cy="12" r="3" />
          </>
        )}
      </svg>
    </button>
  );
}

function formatCountdown(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return "Expired";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function maskToken(token: string | null | undefined): string {
  if (!token) return "—";
  if (token.length <= 8) return token;
  const visible = token.slice(-4);
  return `****************${visible}`;
}

type TokenStatusProps = {
  embedded?: boolean;
};

export default function TokenStatus({ embedded = false }: TokenStatusProps) {
  const [status, setStatus] = useState<Status | null>(() => getCached(CACHE_KEYS.fyersToken));
  const [brokerMeta, setBrokerMeta] = useState<BrokerMeta | null>(null);
  const [lastScanAt, setLastScanAt] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>(() => {
    const h = getCached<{ history?: HistoryRow[] }>(CACHE_KEYS.fyersTokenHistory);
    return h?.history || [];
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [listLoading, setListLoading] = useState(() => !getCached(CACHE_KEYS.fyersTokenHistory));

  const [broker, setBroker] = useState("FYERS");
  const [accessToken, setAccessToken] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [tokenExpiry, setTokenExpiry] = useState("");
  const [notes, setNotes] = useState("");
  const [showAccessToken, setShowAccessToken] = useState(false);
  const [showApiKey, setShowApiKey] = useState(false);
  const [showApiSecret, setShowApiSecret] = useState(false);

  async function load(force = false) {
    try {
      const [res, scanRes, hist, bt] = await Promise.all([
        getTokenStatus({ force }),
        getLatestScan().catch(() => null),
        getTokenHistory().catch(() => ({ history: [] })),
        fetchBrokerToken(broker).catch(() => null),
      ]);
      setStatus(res);
      if (scanRes && scanRes.last_scan_completed_at) {
        setLastScanAt(scanRes.last_scan_completed_at);
      }
      setHistory(hist?.history || []);
      if (bt) {
        setBrokerMeta(bt);
        if (bt.notes) setNotes(bt.notes);
        if (bt.token_expiry) {
          try {
            setTokenExpiry(new Date(bt.token_expiry).toISOString().slice(0, 16));
          } catch {
            /* ignore */
          }
        }
      }
    } catch {
      // Non-critical background load error
    } finally {
      setListLoading(false);
    }
  }

  useEffect(() => {
    void load(false);
    const id = setInterval(() => void load(false), 60000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [broker]);

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const result = await getFyersAuthUrl();
      if (!result.oauth_available || !result.auth_url) {
        setError(result.message || "FYERS OAuth is not configured. Use manual token entry below.");
        setConnecting(false);
        return;
      }
      window.location.href = result.auth_url;
    } catch (e: any) {
      setError(e?.message || "Failed to start FYERS connection.");
      setConnecting(false);
    }
  }

  function clearSecretsFromForm() {
    setAccessToken("");
    setApiSecret("");
  }

  function getMessage(res: any, fallback: string): string {
    return res?.message || (res?.success === false ? res.message : null) || fallback;
  }

  function handleApiError(e: any, fallback: string): string {
    if (e?.json) {
      try {
        const body = typeof e.json === "function" ? null : e.json;
        return body?.message || fallback;
      } catch {
        return fallback;
      }
    }
    return e?.message || fallback;
  }

  async function handleSave(isUpdate = false) {
    setError(null);
    setSuccess(null);
    if (!broker) {
      setError("Broker must be selected");
      return;
    }
    if (!accessToken.trim()) {
      setError("Access token cannot be empty");
      return;
    }
    if (tokenExpiry) {
      const exp = new Date(tokenExpiry);
      if (Number.isNaN(exp.getTime()) || exp.getTime() < Date.now()) {
        setError("Expiry must be a valid future date/time");
        return;
      }
    }
    setBusy(true);
    try {
      const payload = {
        broker,
        access_token: accessToken.trim(),
        api_key: apiKey.trim() || undefined,
        api_secret: apiSecret.trim() || undefined,
        token_expiry: tokenExpiry ? new Date(tokenExpiry).toISOString() : null,
        notes: notes.trim() || undefined,
        validate: broker === "FYERS",
      };
      const result = isUpdate
        ? await updateBrokerToken(payload)
        : await saveBrokerToken(payload);
      setSuccess(getMessage(result, "Token successfully verified and saved."));
      clearSecretsFromForm();
      await load(true);
    } catch (e: any) {
      setError(handleApiError(e, "Failed to save token"));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete stored broker token? Market data may stop until a new token is saved.")) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await deleteBrokerToken(broker);
      setSuccess(getMessage(result, "Token deleted"));
      setBrokerMeta(null);
      clearSecretsFromForm();
      await load(true);
    } catch (e: any) {
      setError(handleApiError(e, "Failed to delete token"));
    } finally {
      setBusy(false);
    }
  }

  async function handleValidate() {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await validateBrokerToken(broker);
      setSuccess(getMessage(res, "Connected Successfully"));
      await load(true);
    } catch (e: any) {
      setError(handleApiError(e, "Validation failed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleTestConnection() {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      if (accessToken.trim()) {
        const res = await testBrokerConnection({
          broker,
          access_token: accessToken.trim(),
          api_key: apiKey.trim() || undefined,
          api_secret: apiSecret.trim() || undefined,
          validate: true,
        });
        setSuccess(getMessage(res, "Connected Successfully"));
      } else {
        const res = await testBrokerConnection({
          broker,
          access_token: "",
          validate: true,
        });
        setSuccess(getMessage(res, "Connected Successfully"));
      }
    } catch (e: any) {
      setError(handleApiError(e, "Connection failed"));
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshToken() {
    await handleValidate();
  }

  const now = new Date();
  const istTime = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const totalMins = istTime.getHours() * 60 + istTime.getMinutes();
  const isEligible = totalMins >= 555 && totalMins <= 1320;

  const connectionLabel =
    brokerMeta?.connection_status ||
    (status?.status === "active" && (status?.expires_in_seconds ?? 0) > 0
      ? "Connected"
      : status?.status === "active"
        ? "Expired"
        : "Disconnected");

  const expiresInSeconds = status?.expires_in_seconds;
  const tokenMask =
    brokerMeta?.token_masked || status?.token_masked || (status?.access_token_active ? "xxxxxxxxxxxx" : null);
  const hasExisting = Boolean(brokerMeta?.exists || status?.access_token_active);

  function InfoRow({ label, value, urgent }: { label: string; value: React.ReactNode; urgent?: boolean }) {
    return (
      <div className="token-mgmt__info-row">
        <span className="token-mgmt__info-label">{label}</span>
        <span className={`token-mgmt__info-value${urgent ? " token-mgmt__info-value--urgent" : ""}`}>{value}</span>
      </div>
    );
  }

  function AlertCard({ type, message, testId }: { type: "success" | "error" | "warning" | "info"; message: string; testId?: string }) {
    const icons = { success: "✓", error: "✕", warning: "⚠", info: "ℹ" };
    return (
      <div className={`token-mgmt__alert token-mgmt__alert--${type}`} role="alert" data-testid={testId}>
        <span className="token-mgmt__alert-icon" aria-hidden>{icons[type]}</span>
        <span>{message}</span>
      </div>
    );
  }

  return (
    <section
      className={embedded ? "token-mgmt token-mgmt--embedded" : "token-mgmt"}
      data-testid="token-management-panel"
    >
      {/* Section Header */}
      <div className="token-mgmt__header">
        <div className="token-mgmt__header-text">
          <p className="ds-label">FYERS TOKEN</p>
          <h2 className="ds-title">Token Management</h2>
        </div>
        <StatusBadge value={connectionLabel} testId="token-status-badge" />
      </div>

      {/* Inline alerts */}
      {error && (
        <AlertCard type="error" message={error} testId="token-error" />
      )}
      {success && (
        <AlertCard type="success" message={success} testId="token-success" />
      )}

      {/* Main content: two columns on desktop */}
      <div className="token-mgmt__columns">
        {/* LEFT COLUMN: Token Information */}
        <div className="token-mgmt__info-card">
          <div className="ds-card__header">
            <div className="ds-card__header-text">
              <p className="ds-label">Token Information</p>
            </div>
          </div>

          <div className="token-mgmt__info-grid">
            <InfoRow label="Broker" value={broker} />
            <InfoRow
              label="Connection Status"
              value={<StatusBadge value={connectionLabel} testId="token-connection-status" />}
            />
            <InfoRow
              label="Token Status"
              value={
                <span className="token-mgmt__mono">
                  {status?.status || (hasExisting ? "Active" : "—")}
                </span>
              }
            />
            <InfoRow
              label="Token Expiry"
              value={
                expiresInSeconds != null ? (
                  <span className={(expiresInSeconds ?? 0) < 3600 ? "token-mgmt__text--warning" : ""}>
                    {formatCountdown(expiresInSeconds)}
                  </span>
                ) : brokerMeta?.token_expiry ? (
                  new Date(brokerMeta.token_expiry).toLocaleString()
                ) : (
                  "—"
                )
              }
              urgent={(expiresInSeconds ?? 0) < 3600 && expiresInSeconds != null}
            />
            <InfoRow
              label="Last Validation"
              value={
                brokerMeta?.last_validated_at
                  ? new Date(brokerMeta.last_validated_at).toLocaleString()
                  : status?.validated_at
                    ? new Date(status.validated_at).toLocaleString()
                    : "—"
              }
            />
            <InfoRow
              label="Last Successful Scan"
              value={lastScanAt ? new Date(lastScanAt).toLocaleString() : "—"}
            />
            <InfoRow
              label="Next Scheduled Scan"
              value={formatNextScan()}
            />
            <InfoRow
              label="Auto Scan Eligible"
              value={
                <Badge tone={isEligible ? "positive" : "neutral"}>
                  {isEligible ? "YES" : "NO"}
                </Badge>
              }
            />
            <InfoRow
              label="Auto Scan Window"
              value="09:15–22:00 IST"
            />
          </div>
        </div>

        {/* RIGHT COLUMN: Form */}
        <div className="token-mgmt__form-card">
          {/* Form header */}
          <div className="ds-card__header">
            <div className="ds-card__header-text">
              <p className="ds-label">Secure form</p>
              <h2 className="ds-title">
                {hasExisting ? "Update Access Token" : "Enter Access Token"}
              </h2>
            </div>
          </div>

          {/* Help text */}
          <p className="token-mgmt__help">
            Paste your manually generated FYERS access token. Tokens are encrypted before storage
            and are never displayed again after saving.
          </p>

          {/* Form fields */}
          <div className="token-mgmt__form">
            <label className="token-mgmt__field">
              <span className="token-mgmt__field-label">Broker</span>
              <select
                className="ds-input"
                value={broker}
                onChange={(e) => setBroker(e.target.value)}
                data-testid="broker-select"
              >
                {BROKERS.map((b) => (
                  <option key={b.value} value={b.value}>{b.label}</option>
                ))}
              </select>
            </label>

            <label className="token-mgmt__field token-mgmt__field--wide">
              <span className="token-mgmt__field-label">Access Token</span>
              <div className="token-secret-wrap">
                <input
                  type={showAccessToken ? "text" : "password"}
                  autoComplete="off"
                  className="ds-input"
                  data-testid="access-token-input"
                  placeholder={hasExisting ? "Enter new token to replace…" : "Paste broker access token"}
                  value={accessToken}
                  onChange={(e) => setAccessToken(e.target.value)}
                />
                <EyeToggle
                  visible={showAccessToken}
                  onToggle={() => setShowAccessToken((v) => !v)}
                  label="access token"
                />
              </div>
            </label>

            <label className="token-mgmt__field">
              <span className="token-mgmt__field-label">API Key</span>
              <div className="token-secret-wrap">
                <input
                  type={showApiKey ? "text" : "password"}
                  autoComplete="off"
                  className="ds-input"
                  data-testid="api-key-input"
                  placeholder="Optional"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
                <EyeToggle visible={showApiKey} onToggle={() => setShowApiKey((v) => !v)} label="API key" />
              </div>
            </label>

            <label className="token-mgmt__field">
              <span className="token-mgmt__field-label">API Secret</span>
              <div className="token-secret-wrap">
                <input
                  type={showApiSecret ? "text" : "password"}
                  autoComplete="off"
                  className="ds-input"
                  data-testid="api-secret-input"
                  placeholder="Optional"
                  value={apiSecret}
                  onChange={(e) => setApiSecret(e.target.value)}
                />
                <EyeToggle
                  visible={showApiSecret}
                  onToggle={() => setShowApiSecret((v) => !v)}
                  label="API secret"
                />
              </div>
            </label>

            <label className="token-mgmt__field">
              <span className="token-mgmt__field-label">Token Expiry</span>
              <input
                type="datetime-local"
                className="ds-input"
                data-testid="token-expiry-input"
                value={tokenExpiry}
                onChange={(e) => setTokenExpiry(e.target.value)}
              />
            </label>

            <label className="token-mgmt__field token-mgmt__field--wide">
              <span className="token-mgmt__field-label">Notes</span>
              <textarea
                className="ds-input token-mgmt__textarea"
                data-testid="token-notes-input"
                placeholder="Optional — e.g. primary trading account"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
              />
            </label>
          </div>

          {/* Buttons */}
          <div className="token-mgmt__actions">
            <Button
              variant="primary"
              data-testid="save-access-token-button"
              disabled={busy || !accessToken.trim()}
              loading={busy}
              onClick={() => void handleSave(false)}
            >
              Save Token
            </Button>
            <Button
              variant="secondary"
              data-testid="update-token-button"
              disabled={busy || !accessToken.trim()}
              onClick={() => void handleSave(true)}
            >
              Update Token
            </Button>
            <Button
              variant="buy"
              data-testid="validate-token-button"
              disabled={busy || !hasExisting}
              onClick={() => void handleValidate()}
            >
              Validate Token
            </Button>
            <Button
              variant="secondary"
              data-testid="refresh-token-button"
              disabled={busy || !hasExisting}
              onClick={() => void handleRefreshToken()}
            >
              Refresh Token
            </Button>
            <Button
              variant="danger"
              data-testid="delete-token-button"
              disabled={busy || !hasExisting}
              onClick={() => void handleDelete()}
            >
              Delete Token
            </Button>
            <Button
              variant="secondary"
              data-testid="test-connection-button"
              disabled={busy || (!accessToken.trim() && !hasExisting)}
              onClick={() => void handleTestConnection()}
            >
              Test Connection
            </Button>
          </div>
        </div>
      </div>

      {/* OAuth Connect */}
      {broker === "FYERS" && (
        <div className="token-mgmt__oauth">
          <Button
            variant="secondary"
            size="sm"
            data-testid="connect-fyers-button"
            onClick={handleConnect}
            disabled={connecting}
            loading={connecting}
          >
            {hasExisting ? "Reconnect via FYERS OAuth" : "Connect to FYERS (OAuth)"}
          </Button>
          <span className="token-mgmt__oauth-hint">
            OAuth is optional — manual token entry above is preferred for this Capital page.
          </span>
        </div>
      )}

      {/* Token History */}
      <div className="token-mgmt__history">
        <div className="ds-card__header">
          <div className="ds-card__header-text">
            <p className="ds-label">History</p>
            <h2 className="ds-title">Token History</h2>
          </div>
        </div>

        {listLoading && history.length === 0 ? (
          <TableSkeleton rows={3} cols={5} />
        ) : (
          <div className="token-mgmt__table-wrap">
            <table className="token-mgmt__table">
              <thead>
                <tr>
                  <th>Saved At</th>
                  <th>Broker</th>
                  <th>Masked Token</th>
                  <th>Status</th>
                  <th>Validated</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {history.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="token-mgmt__table-empty">No history yet</td>
                  </tr>
                ) : (
                  history.map((h) => (
                    <tr key={h.id}>
                      <td className="token-mgmt__table-cell--date">{formatDate(h.saved_at)}</td>
                      <td>{h.broker || broker}</td>
                      <td className="token-mgmt__mono">{maskToken(h.access_token_masked)}</td>
                      <td>
                        <Badge tone={statusTone(h.status)}>
                          {h.status || "—"}
                        </Badge>
                      </td>
                      <td className="token-mgmt__table-cell--center">
                        {h.validated ? (
                          <span className="token-mgmt__check" aria-label="Validated">✓</span>
                        ) : (
                          <span className="token-mgmt__cross" aria-label="Not validated">✕</span>
                        )}
                      </td>
                      <td className="token-mgmt__table-cell--note">{h.note || "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}

function formatNextScan(): string {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const mins = ist.getHours() * 60 + ist.getMinutes();
  if (mins < 555) return "Today at 09:15 IST";
  if (mins < 1320) return "Running";
  return "Tomorrow at 09:15 IST";
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

function statusTone(s: string | null | undefined): "positive" | "neutral" | "warning" | "negative" {
  const v = (s || "").toLowerCase();
  if (v === "active" || v === "connected" || v === "validated") return "positive";
  if (v === "expiring" || v === "expiring soon") return "warning";
  if (v === "expired" || v === "invalid" || v === "error") return "negative";
  return "neutral";
}

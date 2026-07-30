import { useCallback, useEffect, useRef, useState } from "react";
import {
  CRITICAL_FEATURE_KEYS,
  adminErrorMessage,
  isAuthzAdminError,
  listAdminFeatures,
  updateFeaturePermission,
  type FeaturePermission,
} from "../../api_admin";
import { useAuth } from "../../hooks/useAuth";
import { Badge, Button, Card, EmptyState, useToast } from "../../design-system";

function normalizeRoles(roles: string[]): string[] {
  const set = new Set(roles.map((r) => String(r).trim().toLowerCase()).filter(Boolean));
  const out: string[] = [];
  if (set.has("trader")) out.push("trader");
  if (set.has("admin")) out.push("admin");
  return out;
}

function rolesEqual(a: string[], b: string[]): boolean {
  const na = normalizeRoles(a).join(",");
  const nb = normalizeRoles(b).join(",");
  return na === nb;
}

export function FeaturesAdminTab() {
  const toast = useToast();
  const { logout } = useAuth();
  const [items, setItems] = useState<FeaturePermission[]>([]);
  const [draft, setDraft] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  // Toast API identity changes when toasts update — keep stable refs (M-2 loop fix)
  const toastRef = useRef(toast);
  const logoutRef = useRef(logout);
  const sessionClosedRef = useRef(false);
  toastRef.current = toast;
  logoutRef.current = logout;

  const failClosedAuthz = useCallback((e: unknown) => {
    if (sessionClosedRef.current) return;
    sessionClosedRef.current = true;
    toastRef.current.error("Admin session invalid", adminErrorMessage(e));
    logoutRef.current();
  }, []);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (sessionClosedRef.current) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listAdminFeatures({ signal });
      if (signal?.aborted || sessionClosedRef.current) return;
      setItems(data.items);
      const next: Record<string, string[]> = {};
      for (const f of data.items) {
        next[f.feature_key] = normalizeRoles(f.allowed_roles || []);
      }
      setDraft(next);
    } catch (e) {
      if (signal?.aborted || sessionClosedRef.current) return;
      if (isAuthzAdminError(e)) {
        failClosedAuthz(e);
        return;
      }
      setError(adminErrorMessage(e, "Failed to load features"));
      setItems([]);
    } finally {
      if (!signal?.aborted && !sessionClosedRef.current) setLoading(false);
    }
  }, [failClosedAuthz]);

  useEffect(() => {
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [load]);

  function toggleRole(featureKey: string, role: "trader" | "admin", checked: boolean) {
    const critical = CRITICAL_FEATURE_KEYS.has(featureKey);
    if (critical && role === "admin" && !checked) {
      return;
    }
    setDraft((prev) => {
      const current = new Set(prev[featureKey] ?? []);
      if (checked) current.add(role);
      else current.delete(role);
      return { ...prev, [featureKey]: normalizeRoles([...current]) };
    });
  }

  async function save(feature: FeaturePermission) {
    const key = feature.feature_key;
    const allowed_roles = normalizeRoles(draft[key] ?? []);
    if (CRITICAL_FEATURE_KEYS.has(key) && !allowed_roles.includes("admin")) {
      toast.error("Cannot remove admin from critical feature");
      setDraft((d) => ({ ...d, [key]: normalizeRoles(feature.allowed_roles) }));
      return;
    }
    setSavingKey(key);
    try {
      const updated = await updateFeaturePermission(key, { allowed_roles });
      setItems((prev) => prev.map((f) => (f.feature_key === key ? updated : f)));
      setDraft((d) => ({ ...d, [key]: normalizeRoles(updated.allowed_roles) }));
      toast.success("Feature updated", key);
    } catch (e) {
      if (isAuthzAdminError(e)) {
        failClosedAuthz(e);
        return;
      }
      toast.error("Could not update feature", adminErrorMessage(e));
      setDraft((d) => ({ ...d, [key]: normalizeRoles(feature.allowed_roles) }));
    } finally {
      setSavingKey(null);
    }
  }

  if (loading) {
    return (
      <Card data-testid="features-admin-tab">
        <p className="ds-muted" role="status">
          Loading features…
        </p>
      </Card>
    );
  }

  if (error) {
    return (
      <Card data-testid="features-admin-tab">
        <p className="ds-muted" style={{ color: "var(--danger, #f87171)" }}>
          {error}
        </p>
        <Button variant="secondary" size="sm" onClick={() => void load()} style={{ marginTop: 12 }}>
          Retry
        </Button>
      </Card>
    );
  }

  if (items.length === 0) {
    return (
      <div data-testid="features-admin-tab">
        <EmptyState title="No features" description="Feature catalog is empty." />
      </div>
    );
  }

  return (
    <div data-testid="features-admin-tab" className="flex flex-col gap-3">
      {items.map((f) => {
        const roles = draft[f.feature_key] ?? normalizeRoles(f.allowed_roles);
        const critical = CRITICAL_FEATURE_KEYS.has(f.feature_key);
        const dirty = !rolesEqual(roles, f.allowed_roles);
        const saving = savingKey === f.feature_key;
        return (
          <Card key={f.id || f.feature_key}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 12,
                justifyContent: "space-between",
                alignItems: "flex-start",
              }}
            >
              <div style={{ flex: "1 1 220px" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <code style={{ fontSize: 14 }}>{f.feature_key}</code>
                  {critical ? <Badge tone="warning">critical</Badge> : null}
                  <Badge tone={f.is_active ? "positive" : "neutral"}>
                    {f.is_active ? "active" : "inactive"}
                  </Badge>
                </div>
                <p className="ds-muted" style={{ marginTop: 6, fontSize: 13 }}>
                  {f.description}
                </p>
                <p className="ds-caption ds-muted" style={{ marginTop: 4 }}>
                  Active status is read-only in this panel
                </p>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 160 }}>
                <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14 }}>
                  <input
                    type="checkbox"
                    checked={roles.includes("trader")}
                    onChange={(e) => toggleRole(f.feature_key, "trader", e.target.checked)}
                    data-testid={`feat-trader-${f.feature_key}`}
                  />
                  Trader
                </label>
                <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14 }}>
                  <input
                    type="checkbox"
                    checked={roles.includes("admin")}
                    disabled={critical}
                    onChange={(e) => toggleRole(f.feature_key, "admin", e.target.checked)}
                    data-testid={`feat-admin-${f.feature_key}`}
                  />
                  Admin
                  {critical ? (
                    <span className="ds-caption ds-muted">(required)</span>
                  ) : null}
                </label>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={!dirty || saving}
                  loading={saving}
                  onClick={() => void save(f)}
                  data-testid={`feat-save-${f.feature_key}`}
                >
                  Save
                </Button>
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}

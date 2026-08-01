import { useCallback, useEffect, useRef, useState } from "react";
import {
  adminErrorMessage,
  isAuthzAdminError,
  listAdminUsers,
  updateUserRole,
  type AdminRole,
  type AdminUser,
} from "../../api_admin";
import { useAuth } from "../../hooks/useAuth";
import { Badge, Button, Card, EmptyState, useToast } from "../../design-system";
import { RoleChangeModal } from "./RoleChangeModal";

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export function UsersAdminTab() {
  const toast = useToast();
  const { logout } = useAuth();
  const [items, setItems] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [size] = useState(20);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [confirmUser, setConfirmUser] = useState<AdminUser | null>(null);
  const [confirmRole, setConfirmRole] = useState<AdminRole | null>(null);
  const searchInitialized = useRef(false);
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
      const data = await listAdminUsers({
        page,
        size,
        search: search || undefined,
        signal,
      });
      if (signal?.aborted || sessionClosedRef.current) return;
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      if (signal?.aborted || sessionClosedRef.current) return;
      if (isAuthzAdminError(e)) {
        // Hardening M-2: hard fail closed when session is not admin
        failClosedAuthz(e);
        return;
      }
      setError(adminErrorMessage(e, "Failed to load users"));
      setItems([]);
      setTotal(0);
    } finally {
      if (!signal?.aborted && !sessionClosedRef.current) setLoading(false);
    }
  }, [page, size, search, failClosedAuthz]);

  // Load with abort on unmount / dependency change (M-1)
  useEffect(() => {
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
  }, [load]);

  // Debounce search — only reset page when search value actually changes (M-4)
  useEffect(() => {
    const t = window.setTimeout(() => {
      const next = searchInput.trim();
      if (!searchInitialized.current) {
        searchInitialized.current = true;
        if (next === search) return;
      }
      if (next === search) return;
      setPage(1);
      setSearch(next);
    }, 300);
    return () => window.clearTimeout(t);
  }, [searchInput, search]);

  function openChange(user: AdminUser, next: AdminRole) {
    if (user.role === next) return;
    setConfirmUser(user);
    setConfirmRole(next);
  }

  async function confirmChange() {
    if (!confirmUser || !confirmRole) return;
    setPendingId(confirmUser.id);
    try {
      const updated = await updateUserRole(confirmUser.id, confirmRole);
      setItems((prev) => prev.map((u) => (u.id === updated.id ? { ...u, ...updated } : u)));
      toast.success("Role updated", `${updated.email} is now ${updated.role}`);
      setConfirmUser(null);
      setConfirmRole(null);
    } catch (e) {
      if (isAuthzAdminError(e)) {
        failClosedAuthz(e);
        return;
      }
      toast.error("Could not change role", adminErrorMessage(e));
    } finally {
      setPendingId(null);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / size) || 1);

  return (
    <div data-testid="users-admin-tab">
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          marginBottom: 16,
          alignItems: "center",
        }}
      >
        <input
          type="search"
          className="ds-input"
          placeholder="Search email or name…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          aria-label="Search users"
          data-testid="users-search"
          style={{ minWidth: 220, flex: "1 1 200px" }}
        />
        <span className="ds-muted" style={{ fontSize: 13 }}>
          {total} user{total === 1 ? "" : "s"}
        </span>
        <Button variant="ghost" size="sm" onClick={() => void load()} disabled={loading}>
          Refresh
        </Button>
      </div>

      {loading ? (
        <Card>
          <p className="ds-muted" role="status">
            Loading users…
          </p>
        </Card>
      ) : error ? (
        <Card>
          <p className="ds-muted" style={{ color: "var(--danger, #f87171)" }}>
            {error}
          </p>
          <Button variant="secondary" size="sm" onClick={() => void load()} style={{ marginTop: 12 }}>
            Retry
          </Button>
        </Card>
      ) : items.length === 0 ? (
        <EmptyState title="No users found" description="Try a different search or clear the filter." />
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-left" style={{ borderCollapse: "collapse", minWidth: 640 }}>
            <thead>
              <tr className="ds-muted" style={{ fontSize: 12, textTransform: "uppercase" }}>
                <th style={{ padding: "8px 12px" }}>Email</th>
                <th style={{ padding: "8px 12px" }}>Name</th>
                <th style={{ padding: "8px 12px" }}>Role</th>
                <th style={{ padding: "8px 12px" }}>Active</th>
                <th style={{ padding: "8px 12px" }}>Created</th>
                <th style={{ padding: "8px 12px" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.id} style={{ borderTop: "1px solid var(--border, #243041)" }}>
                  <td style={{ padding: "10px 12px", fontSize: 14 }}>{u.email}</td>
                  <td style={{ padding: "10px 12px", fontSize: 14 }}>{u.full_name}</td>
                  <td style={{ padding: "10px 12px" }}>
                    <Badge tone={u.role === "admin" ? "warning" : "neutral"}>{u.role}</Badge>
                  </td>
                  <td style={{ padding: "10px 12px", fontSize: 13 }}>
                    {u.is_active ? "Yes" : "No"}
                  </td>
                  <td style={{ padding: "10px 12px", fontSize: 13 }} className="ds-muted">
                    {formatDate(u.created_at)}
                  </td>
                  <td style={{ padding: "10px 12px" }}>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {u.role !== "admin" ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={pendingId === u.id}
                          onClick={() => openChange(u, "admin")}
                          data-testid={`promote-${u.id}`}
                        >
                          Make admin
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={pendingId === u.id}
                          onClick={() => openChange(u, "trader")}
                          data-testid={`demote-${u.id}`}
                        >
                          Make trader
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {!loading && !error && totalPages > 1 ? (
        <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center" }}>
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span className="ds-muted" style={{ fontSize: 13 }}>
            Page {page} of {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      ) : null}

      <RoleChangeModal
        open={Boolean(confirmUser && confirmRole)}
        user={confirmUser}
        nextRole={confirmRole}
        loading={Boolean(pendingId)}
        onClose={() => {
          if (pendingId) return;
          setConfirmUser(null);
          setConfirmRole(null);
        }}
        onConfirm={() => void confirmChange()}
      />
    </div>
  );
}

import { Link, Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../hooks/useAuth";
import { Card } from "../design-system";

/**
 * Admin-only routes — real role gate (Sprint 4).
 * Developer mode does NOT unlock these destinations.
 */
export function AdminRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading, role } = useAuth();
  const location = useLocation();

  if (isLoading && !isAuthenticated) {
    return (
      <div
        className="flex h-screen w-full flex-col items-center justify-center gap-3"
        style={{ background: "var(--bg, #0e1116)", color: "var(--text-muted, #9eacbb)" }}
        role="status"
        aria-live="polite"
      >
        <div className="app-skel" style={{ width: 48, height: 48, borderRadius: "50%" }} aria-hidden />
        <span style={{ fontSize: 13, opacity: 0.8 }}>Checking admin access…</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (role !== "admin") {
    return <ForbiddenAdmin />;
  }

  return <>{children}</>;
}

export function ForbiddenAdmin() {
  return (
    <div className="page-container" data-testid="admin-forbidden">
      <Card>
        <p className="ds-label">Restricted</p>
        <h1 className="ds-heading">Admin access required</h1>
        <p className="ds-muted" style={{ marginTop: 8, marginBottom: 16 }}>
          You need an administrator role to open this page. Contact an admin if you believe this is a
          mistake.
        </p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {/* Hardening H-2: SPA Link (no full reload, no nested invalid button markup) */}
          <Link
            to="/scanner"
            className="ds-btn ds-btn--primary ds-btn--md"
            data-testid="admin-forbidden-back"
          >
            <span className="ds-btn__label">Back to Scanner</span>
          </Link>
        </div>
      </Card>
    </div>
  );
}

/** @deprecated Prefer Navigate to /scanner — kept for import compatibility */
export function AdminRedirect() {
  return <Navigate to="/scanner" replace />;
}

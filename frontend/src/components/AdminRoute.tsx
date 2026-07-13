import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useDeveloperMode } from "../hooks/useDeveloperMode";
import { Card, Button } from "../design-system";

/**
 * Engineering pages — only when Developer mode is enabled in the sidebar.
 * Retail users never see infrastructure destinations in nav; this also blocks deep links.
 */
export function AdminRoute({ children }: { children: ReactNode }) {
  const { developerMode, setDeveloperMode } = useDeveloperMode();

  if (!developerMode) {
    return (
      <div className="page-container">
        <Card>
          <p className="ds-label">Restricted</p>
          <h1 className="ds-heading">Developer tools</h1>
          <p className="ds-muted" style={{ marginTop: 8, marginBottom: 16 }}>
            System logs, central command, and infrastructure controls are hidden for retail trading.
            Enable Developer mode in the sidebar to access engineering pages.
          </p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button variant="secondary" onClick={() => setDeveloperMode(true)}>
              Enable developer mode
            </Button>
            <Button variant="ghost" onClick={() => undefined}>
              <a href="/scanner" style={{ color: "inherit", textDecoration: "none" }}>
                Back to Scanner
              </a>
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  return <>{children}</>;
}

export function AdminRedirect() {
  return <Navigate to="/scanner" replace />;
}

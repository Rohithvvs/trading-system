import { Link, useLocation } from "react-router-dom";
import { CANONICAL_ROUTES } from "../routes/routesConfig";

export function Breadcrumbs() {
  const location = useLocation();
  const path = location.pathname;

  const currentRoute = CANONICAL_ROUTES.find(
    (r) => r.path === path || (r.path !== "/" && path.startsWith(r.path)),
  );

  const domainLabels: Record<string, string> = {
    overview: "Overview",
    research: "Research & Discovery",
    execution: "Execution & Portfolio",
    analytics: "Quantitative Analytics",
    system: "Platform Control",
  };

  const domain = currentRoute?.domain;
  const domainLabel = domain ? domainLabels[domain] : null;

  return (
    <nav aria-label="Breadcrumb" className="breadcrumbs-nav" style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.85rem", color: "var(--text-muted)" }}>
      <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none" }} hover-style={{ color: "var(--accent)" }}>
        Home
      </Link>
      {domainLabel && domain !== "overview" && (
        <>
          <span style={{ opacity: 0.5 }}>/</span>
          <span>{domainLabel}</span>
        </>
      )}
      {currentRoute && currentRoute.path !== "/" && (
        <>
          <span style={{ opacity: 0.5 }}>/</span>
          <span style={{ color: "var(--text)", fontWeight: 500 }}>{currentRoute.label}</span>
        </>
      )}
    </nav>
  );
}

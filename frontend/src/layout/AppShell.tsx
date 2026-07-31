import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "../hooks/useTheme";
import { useDensity } from "../hooks/useDensity";
import { useDeveloperMode } from "../hooks/useDeveloperMode";
import { PLATFORM_NAV_DOMAINS, isNavActive, type NavItem } from "./navConfig";
import { ThemeToggle } from "../components/ThemeToggle";
import { Breadcrumbs } from "../components/Breadcrumbs";
import { GlobalSearch } from "../components/GlobalSearch";
import { navigateToPaperOrder } from "../utils/paperOrderNavigation";

type Props = {
  children: ReactNode;
  /** Optional top bar actions (search, BUY CTA, etc.) */
  topActions?: ReactNode;
  title?: string;
};

const SIDEBAR_STORAGE_KEY = "ui_sidebar_collapsed";

function readSidebarCollapsed(): boolean {
  try {
    const v = localStorage.getItem(SIDEBAR_STORAGE_KEY);
    if (v === "1") return true;
    if (v === "0") return false;
  } catch {
    /* ignore */
  }
  if (typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(max-width: 1280px) and (min-width: 769px)").matches) {
    return true;
  }
  return false;
}

export function AppShell({ children, topActions, title }: Props) {
  const { theme } = useTheme();
  const { density, setDensity } = useDensity();
  const { developerMode, setDeveloperMode } = useDeveloperMode();
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() =>
    typeof window === "undefined" ? false : readSidebarCollapsed(),
  );
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarCollapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  function toggleSidebar() {
    setSidebarCollapsed((c) => !c);
  }

  const mobileNavItems: NavItem[] = PLATFORM_NAV_DOMAINS.flatMap((d) => d.items).slice(0, 4);

  return (
    <div
      className={[
        "app-shell-v2",
        sidebarCollapsed ? "app-shell-v2--collapsed" : "app-shell-v2--expanded",
        mobileMenuOpen ? "app-shell-v2--mobile-open" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-theme-active={theme}
      data-sidebar={sidebarCollapsed ? "collapsed" : "expanded"}
    >
      {/* Desktop / tablet sidebar */}
      <aside className="app-sidebar" aria-label="Main navigation" data-collapsed={sidebarCollapsed ? "true" : "false"}>
        <div className="app-sidebar__brand">
          <Link to="/" className="app-brand-link" aria-label="Go to Dashboard">
            <span className="app-brand-mark" aria-hidden>
              AI
            </span>
            <span className="app-brand-text">QuantLab</span>
          </Link>
          <button
            type="button"
            className="app-sidebar__collapse ds-icon-btn"
            onClick={toggleSidebar}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={sidebarCollapsed}
            title={sidebarCollapsed ? "Expand" : "Collapse"}
            data-testid="sidebar-collapse-toggle"
          >
            {sidebarCollapsed ? "»" : "«"}
          </button>
        </div>

        <nav className="app-sidebar__nav">
          {PLATFORM_NAV_DOMAINS.map((domain) => (
            <div key={domain.id} className="app-sidebar__domain-group" style={{ marginBottom: "12px" }}>
              {!sidebarCollapsed && (
                <div
                  className="ds-caption"
                  style={{
                    padding: "4px 12px",
                    textTransform: "uppercase",
                    fontSize: "0.7rem",
                    fontWeight: 600,
                    letterSpacing: "0.05em",
                    opacity: 0.6,
                  }}
                >
                  {domain.label}
                </div>
              )}
              {domain.items.map((item) => {
                const active = isNavActive(location.pathname, item);
                return (
                  <NavLink
                    key={item.id}
                    to={item.path}
                    data-testid={item.testId}
                    className={`app-sidebar__link ${active ? "is-active" : ""}`}
                    title={item.label}
                  >
                    <span className="app-sidebar__icon">{item.icon}</span>
                    <span className="app-sidebar__label">{item.label}</span>
                  </NavLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="app-sidebar__footer">
          <div className="app-sidebar__meta">
            <label className="app-density-toggle">
              <span className="ds-caption app-sidebar__meta-label">Density</span>
              <select
                value={density}
                onChange={(e) => setDensity(e.target.value as "comfortable" | "compact")}
                aria-label="UI density"
              >
                <option value="comfortable">Comfortable</option>
                <option value="compact">Compact</option>
              </select>
            </label>
            <label className="app-dev-toggle" title="Developer mode">
              <input
                type="checkbox"
                checked={developerMode}
                onChange={(e) => setDeveloperMode(e.target.checked)}
              />
              <span className="ds-caption app-sidebar__meta-label">Developer mode</span>
            </label>
          </div>
          <ThemeToggle />
        </div>
      </aside>

      {/* Main column */}
      <div className="app-main-column">
        <header className="app-topbar">
          <div className="app-topbar__left" style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <button
              type="button"
              className="ds-icon-btn app-topbar__menu"
              aria-label="Open navigation"
              onClick={() => setMobileMenuOpen(true)}
            >
              ☰
            </button>
            <Breadcrumbs />
            {title ? <h1 className="app-topbar__title" style={{ fontSize: "1.1rem", margin: 0 }}>{title}</h1> : null}
          </div>
          <div className="app-topbar__actions" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <GlobalSearch />
            {topActions}
            <button
              type="button"
              className="ds-btn ds-btn--buy ds-btn--sm"
              data-testid="global-buy-cta"
              onClick={() =>
                navigateToPaperOrder(navigate, {
                  side: "BUY",
                  returnTo: `${location.pathname}${location.search || ""}`,
                })
              }
            >
              BUY
            </button>
            <button
              type="button"
              className="ds-btn ds-btn--sell ds-btn--sm"
              data-testid="global-sell-cta"
              onClick={() =>
                navigateToPaperOrder(navigate, {
                  side: "SELL",
                  returnTo: `${location.pathname}${location.search || ""}`,
                })
              }
            >
              SELL
            </button>
          </div>
        </header>

        <div className="app-content">{children}</div>
      </div>

      {/* Mobile drawer overlay */}
      {mobileMenuOpen ? (
        <button
          type="button"
          className="app-mobile-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileMenuOpen(false)}
        />
      ) : null}

      {/* Floating scan button — mobile only */}
      <button
        type="button"
        className="floating-scan-btn"
        aria-label="Run scanner"
        title="Run scanner"
        onClick={() => navigate("/research/scanner")}
      >
        ⚡
      </button>

      {/* Mobile bottom navigation */}
      <nav className="app-bottom-nav" aria-label="Primary">
        {mobileNavItems.map((item) => {
          const active = isNavActive(location.pathname, item);
          return (
            <NavLink
              key={item.id}
              to={item.path}
              data-testid={`${item.testId}-mobile`}
              className={`app-bottom-nav__item ${active ? "is-active" : ""}`}
            >
              <span className="app-bottom-nav__icon">{item.icon}</span>
              <span className="app-bottom-nav__label">{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}

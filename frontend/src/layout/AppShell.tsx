import { useEffect, useRef, useState, useCallback, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import { useDensity } from "../hooks/useDensity";
import { ADMIN_NAV, RETAIL_NAV, isNavActive } from "./navConfig";
import { ThemeToggle } from "../components/ThemeToggle";
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
  // Default: collapsed only on narrow desktop (≤1280); mobile uses drawer
  if (typeof window !== "undefined" && window.matchMedia("(max-width: 1280px) and (min-width: 769px)").matches) {
    return true;
  }
  return false;
}

export function AppShell({ children, topActions, title }: Props) {
  const { user, logout, role } = useAuth();
  const { theme } = useTheme();
  const { density, setDensity } = useDensity();
  const location = useLocation();
  const isAdmin = role === "admin";
  const navigate = useNavigate();
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() =>
    typeof window === "undefined" ? false : readSidebarCollapsed(),
  );
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);

  // Persist collapse preference — never fight the toggle with media-query forced state
  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, sidebarCollapsed ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    setMobileMenuOpen(false);
    setProfileOpen(false);
  }, [location.pathname]);

  function toggleSidebar() {
    setSidebarCollapsed((c) => !c);
  }

  const profileRef = useRef<HTMLDivElement>(null);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(max-width: 768px)").matches,
  );

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 768px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Click outside + ESC to close profile menu
  useEffect(() => {
    if (!profileOpen) return;
    const handler = (e: MouseEvent | TouchEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
    };
    const keyHandler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setProfileOpen(false);
    };
    document.addEventListener("mousedown", handler);
    document.addEventListener("touchstart", handler);
    document.addEventListener("keydown", keyHandler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("touchstart", handler);
      document.removeEventListener("keydown", keyHandler);
    };
  }, [profileOpen]);

  const initials = (user?.full_name || user?.email || "U").slice(0, 1).toUpperCase();
  // Sprint 4: admin destinations by real role — not developerMode
  const navItems = isAdmin ? [...RETAIL_NAV, ...ADMIN_NAV] : RETAIL_NAV;

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
          <Link to="/scanner" className="app-brand-link" aria-label="Go to Scanner">
            <span className="app-brand-mark" aria-hidden>
              TS
            </span>
            <span className="app-brand-text">TradeDesk</span>
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
          {navItems.map((item) => {
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
            {/* Developer mode toggle hidden (Sprint 4): unused for routes; never unlocks /admin/* */}
          </div>
          <ThemeToggle />
        </div>
      </aside>

      {/* Main column */}
      <div className="app-main-column">
        <header className="app-topbar">
          <div className="app-topbar__left">
            <button
              type="button"
              className="ds-icon-btn app-topbar__menu"
              aria-label="Open navigation"
              onClick={() => setMobileMenuOpen(true)}
            >
              ☰
            </button>
            {title ? <h1 className="app-topbar__title">{title}</h1> : null}
          </div>
          <div className="app-topbar__actions">
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
            <div className="nav-profile-wrap" ref={profileRef}>
              <button
                type="button"
                data-testid="nav-profile-menu"
                className="nav-profile-btn app-topbar__profile"
                onClick={() => setProfileOpen((o) => !o)}
                aria-expanded={profileOpen}
                aria-haspopup="menu"
              >
                <span className="nav-avatar" aria-hidden>
                  {initials}
                </span>
                <span className="nav-profile-label app-topbar__name">
                  {user?.full_name?.split(" ")[0] || "Profile"}
                </span>
              </button>
              {profileOpen ? (
                <div className={`nav-profile-menu ${isMobile ? "nav-profile-menu--mobile" : ""}`} role="menu">
                  <button type="button" role="menuitem" onClick={() => { setProfileOpen(false); navigate("/profile"); }}>
                    Profile
                  </button>
                  <button type="button" role="menuitem" onClick={() => { setProfileOpen(false); navigate("/profile?section=preferences"); }}>
                    Preferences
                  </button>
                  <button type="button" role="menuitem" onClick={() => { setProfileOpen(false); navigate("/paper"); }}>
                    Paper Desk
                  </button>
                  {isAdmin ? (
                    <button
                      type="button"
                      role="menuitem"
                      data-testid="nav-admin-panel-profile"
                      onClick={() => {
                        setProfileOpen(false);
                        navigate("/admin");
                      }}
                    >
                      Admin
                    </button>
                  ) : null}
                  <button
                    type="button"
                    role="menuitem"
                    className="danger"
                    onClick={() => {
                      setProfileOpen(false);
                      logout();
                    }}
                  >
                    Sign out
                  </button>
                </div>
              ) : null}
            </div>
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
        onClick={() => navigate("/scanner")}
      >
        ⚡
      </button>

      {/* Mobile bottom navigation */}
      <nav className="app-bottom-nav" aria-label="Primary">
        {RETAIL_NAV.slice(0, 4).map((item) => {
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
        <NavLink
          to="/profile"
          data-testid="nav-profile-mobile"
          className={`app-bottom-nav__item ${location.pathname.startsWith("/profile") ? "is-active" : ""}`}
        >
          <span className="app-bottom-nav__icon" aria-hidden>
            <span className="nav-avatar nav-avatar--sm">{initials}</span>
          </span>
          <span className="app-bottom-nav__label">Profile</span>
        </NavLink>
      </nav>
    </div>
  );
}

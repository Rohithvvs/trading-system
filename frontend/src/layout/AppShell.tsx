import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import { MarketIndicesStrip } from "./MarketIndicesStrip";
import { SymbolSearchBar } from "../components/retail/SymbolSearchBar";
import { NotificationBellRetail } from "../components/retail/NotificationBellRetail";
import { fetchUnreadCount } from "../api_retail";

const NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/watchlists", label: "Watchlists" },
  { to: "/quotes", label: "Quotes" },
  { to: "/chart", label: "Chart" },
  { to: "/holdings", label: "Holdings" },
  { to: "/positions", label: "Positions" },
  { to: "/orders", label: "Orders" },
  { to: "/heatmap", label: "Heatmap" },
  { to: "/scanner", label: "Scanner" },
  { to: "/paper-trading", label: "Trade" },
  { to: "/portfolio", label: "Portfolio" },
  { to: "/alerts", label: "Alerts" },
];

export function AppShell() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void fetchUnreadCount()
        .then((r) => {
          if (!cancelled) setUnread(r.unread_count);
        })
        .catch(() => undefined);
    };
    load();
    const id = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="app-shell retail-shell">
      <MarketIndicesStrip />
      <header className="retail-topbar">
        <div className="retail-topbar-inner">
          <button type="button" className="retail-brand" onClick={() => navigate("/dashboard")}>
            <span className="retail-brand-mark">TS</span>
            <span className="retail-brand-name">Trading System</span>
          </button>

          <nav className="retail-nav" aria-label="Primary">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `retail-nav-link ${isActive ? "is-active" : ""}`}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="retail-topbar-actions">
            <SymbolSearchBar
              onSelect={(symbol) => {
                navigate(`/chart/${symbol}`);
              }}
            />
            <NotificationBellRetail unread={unread} onOpen={() => navigate("/alerts")} />
            <button type="button" className="button ghost-button retail-icon-btn" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === "dark" ? "Light" : "Dark"}
            </button>
            <div className="nav-profile-wrap">
              <button
                type="button"
                className="main-nav-tab nav-profile-btn"
                onClick={() => setMenuOpen((o) => !o)}
                aria-expanded={menuOpen}
              >
                <span className="nav-avatar">{(user?.full_name || user?.email || "U").slice(0, 1).toUpperCase()}</span>
                <span className="nav-profile-label">{user?.full_name?.split(" ")[0] || "Profile"}</span>
              </button>
              {menuOpen ? (
                <div className="nav-profile-menu" role="menu">
                  <button type="button" role="menuitem" onClick={() => { navigate("/profile"); setMenuOpen(false); }}>Profile</button>
                  <button type="button" role="menuitem" onClick={() => { navigate("/settings"); setMenuOpen(false); }}>Settings</button>
                  <button type="button" role="menuitem" onClick={() => { navigate("/reports"); setMenuOpen(false); }}>Reports</button>
                  <button type="button" role="menuitem" onClick={() => { navigate("/trade-journal"); setMenuOpen(false); }}>Trade Journal</button>
                  <button type="button" role="menuitem" onClick={() => { navigate("/logs"); setMenuOpen(false); }}>System Logs</button>
                  <button type="button" role="menuitem" className="danger" onClick={() => { setMenuOpen(false); logout(); }}>Sign out</button>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      <div className="app-main-scroll retail-main">
        <Outlet />
      </div>
    </div>
  );
}

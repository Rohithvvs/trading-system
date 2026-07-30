import type { ReactNode } from "react";

export type NavItem = {
  id: string;
  label: string;
  path: string;
  /** Match path prefix for active state */
  match?: string;
  icon: ReactNode;
  testId: string;
};

const icon = (d: string) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={d} />
  </svg>
);

/** Retail primary navigation — Markets, Scanner, Watchlist, Paper Desk, Performance, Profile */
export const RETAIL_NAV: NavItem[] = [
  {
    id: "markets",
    label: "Markets",
    path: "/markets",
    match: "/markets",
    testId: "nav-markets",
    icon: icon("M3 3v18h18 M7 14l4-4 3 3 5-6"),
  },
  {
    id: "scanner",
    label: "Scanner",
    path: "/scanner",
    match: "/scanner",
    testId: "nav-scanner",
    icon: icon("M11 5a7 7 0 1 0 4.5 12.3L21 21 M11 8v3h3"),
  },
  {
    id: "paper",
    label: "Paper Desk",
    path: "/paper",
    match: "/paper",
    testId: "nav-paper-trading",
    icon: icon("M4 19h16 M6 16V8l6-4 6 4v8 M10 12h4"),
  },
  {
    id: "performance",
    label: "Performance",
    path: "/performance",
    match: "/performance",
    testId: "nav-performance",
    icon: icon("M4 19V5 M8 19v-8 M12 19v-5 M16 19V9 M20 19v-3"),
  },
  {
    id: "profile",
    label: "Profile",
    path: "/profile",
    match: "/profile",
    testId: "nav-profile",
    icon: icon("M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4z M4 20a8 8 0 0 1 16 0"),
  },
];

/** Admin / ops — only when user.role === "admin" (Sprint 4) */
export const ADMIN_NAV: NavItem[] = [
  {
    id: "admin-panel",
    label: "Admin",
    path: "/admin",
    match: "/admin",
    testId: "nav-admin-panel",
    icon: icon("M12 1l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 8h7z"),
  },
  {
    id: "admin-command",
    label: "Central Command",
    path: "/admin/command",
    match: "/admin/command",
    testId: "nav-central-command",
    icon: icon("M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"),
  },
  {
    id: "admin-logs",
    label: "System Logs",
    path: "/admin/logs",
    match: "/admin/logs",
    testId: "nav-system-logs",
    icon: icon("M4 6h16 M4 12h16 M4 18h10"),
  },
  {
    id: "admin-diagnostics",
    label: "Diagnostics",
    path: "/diagnostics",
    match: "/diagnostics",
    testId: "nav-diagnostics",
    icon: icon("M12 2v4 M12 18v4 M4.93 4.93l2.83 2.83 M16.24 16.24l2.83 2.83 M2 12h4 M18 12h4 M4.93 19.07l2.83-2.83 M16.24 7.76l2.83-2.83"),
  },
];

export function isNavActive(pathname: string, item: NavItem): boolean {
  const m = item.match ?? item.path;
  if (m === "/") return pathname === "/";
  // Exact match for /admin so /admin/logs does not highlight Admin panel
  if (item.id === "admin-panel") {
    return pathname === "/admin" || pathname.startsWith("/admin?");
  }
  return pathname === m || pathname.startsWith(`${m}/`);
}

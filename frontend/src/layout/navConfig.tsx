import type { ReactNode } from "react";

export type NavItem = {
  id: string;
  label: string;
  path: string;
  /** Match path prefix for active state */
  match?: string;
  icon: ReactNode;
  testId: string;
  domain?: string;
};

export type NavDomain = {
  id: string;
  label: string;
  items: NavItem[];
};

const icon = (d: string) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={d} />
  </svg>
);

export const PLATFORM_NAV_DOMAINS: NavDomain[] = [
  {
    id: "overview",
    label: "Overview",
    items: [
      {
        id: "dashboard",
        label: "Dashboard",
        path: "/",
        match: "/",
        testId: "nav-dashboard",
        icon: icon("M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10"),
      },
    ],
  },
  {
    id: "research",
    label: "Research & Discovery",
    items: [
      {
        id: "scanner",
        label: "Opportunity Scanner",
        path: "/research/scanner",
        match: "/research/scanner",
        testId: "nav-scanner",
        icon: icon("M11 5a7 7 0 1 0 4.5 12.3L21 21 M11 8v3h3"),
      },
      {
        id: "workstation",
        label: "Stock Workstation",
        path: "/research/workstation",
        match: "/research/workstation",
        testId: "nav-workstation",
        icon: icon("M3 3v18h18 M7 14l4-4 3 3 5-6"),
      },
      {
        id: "markets",
        label: "Market Watch & Sectors",
        path: "/research/markets",
        match: "/research/markets",
        testId: "nav-markets",
        icon: icon("M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"),
      },
    ],
  },
  {
    id: "execution",
    label: "Execution & Portfolio",
    items: [
      {
        id: "paper",
        label: "Paper Trading Desk",
        path: "/trading/paper-desk",
        match: "/trading/paper-desk",
        testId: "nav-paper-trading",
        icon: icon("M4 19h16 M6 16V8l6-4 6 4v8 M10 12h4"),
      },
      {
        id: "watchlist",
        label: "Watchlist",
        path: "/trading/watchlist",
        match: "/trading/watchlist",
        testId: "nav-watchlist",
        icon: icon("M12 2l3 7h7l-5.5 4.5L18 21l-6-4-6 4 1.5-7.5L2 9h7z"),
      },
    ],
  },
  {
    id: "analytics",
    label: "Quantitative Analytics",
    items: [
      {
        id: "performance",
        label: "Quant Analytics",
        path: "/analytics/performance",
        match: "/analytics/performance",
        testId: "nav-performance",
        icon: icon("M4 19V5 M8 19v-8 M12 19v-5 M16 19V9 M20 19v-3"),
      },
    ],
  },
  {
    id: "system",
    label: "Platform Control",
    items: [
      {
        id: "diagnostics",
        label: "System Diagnostics",
        path: "/system/diagnostics",
        match: "/system/diagnostics",
        testId: "nav-diagnostics",
        icon: icon("M12 2v4 M12 18v4 M4.93 4.93l2.83 2.83 M16.24 16.24l2.83 2.83 M2 12h4 M18 12h4 M4.93 19.07l2.83-2.83 M16.24 7.76l2.83-2.83"),
      },
      {
        id: "logs",
        label: "System Logs",
        path: "/system/logs",
        match: "/system/logs",
        testId: "nav-system-logs",
        icon: icon("M4 6h16 M4 12h16 M4 18h10"),
      },
    ],
  },
];

export const PLATFORM_NAV: NavItem[] = PLATFORM_NAV_DOMAINS.flatMap((d) => d.items);

/** Backward compatibility aliases for legacy components and tests */
export const RETAIL_NAV: NavItem[] = [
  ...PLATFORM_NAV_DOMAINS[0].items,
  ...PLATFORM_NAV_DOMAINS[1].items,
  ...PLATFORM_NAV_DOMAINS[2].items,
  ...PLATFORM_NAV_DOMAINS[3].items,
];

export const ADMIN_NAV: NavItem[] = [
  ...PLATFORM_NAV_DOMAINS[4].items,
];

export function isNavActive(pathname: string, item: NavItem): boolean {
  const m = item.match ?? item.path;
  if (m === "/") return pathname === "/";
  return pathname === m || pathname.startsWith(`${m}/`);
}

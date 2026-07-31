export interface RouteConfig {
  path: string;
  label: string;
  domain: "overview" | "research" | "execution" | "analytics" | "system";
  isCanonical: boolean;
  redirectTo?: string;
  testId: string;
}

export const CANONICAL_ROUTES: RouteConfig[] = [
  { path: "/", label: "Dashboard", domain: "overview", isCanonical: true, testId: "route-dashboard" },
  { path: "/research/scanner", label: "Opportunity Scanner", domain: "research", isCanonical: true, testId: "route-scanner" },
  { path: "/research/workstation", label: "Stock Workstation", domain: "research", isCanonical: true, testId: "route-workstation" },
  { path: "/research/markets", label: "Market Watch & Sectors", domain: "research", isCanonical: true, testId: "route-markets" },
  { path: "/trading/paper-desk", label: "Paper Trading Desk", domain: "execution", isCanonical: true, testId: "route-paper-desk" },
  { path: "/paper-order", label: "Paper Order Ticket", domain: "execution", isCanonical: true, testId: "route-paper-order" },
  { path: "/analytics/performance", label: "Quant Analytics", domain: "analytics", isCanonical: true, testId: "route-performance" },
  { path: "/system/diagnostics", label: "System Diagnostics", domain: "system", isCanonical: true, testId: "route-diagnostics" },
  { path: "/system/logs", label: "System Logs", domain: "system", isCanonical: true, testId: "route-logs" },
];

export const REDIRECT_ROUTES: Record<string, string> = {
  "/home": "/",
  "/admin/command": "/",
  "/scanner": "/research/scanner",
  "/markets": "/research/markets",
  "/paper": "/trading/paper-desk",
  "/watchlist": "/trading/paper-desk?tab=watchlist",
  "/trading/watchlist": "/trading/paper-desk?tab=watchlist",
  "/performance": "/analytics/performance",
  "/diagnostics": "/system/diagnostics",
  "/logs": "/system/logs",
  "/admin/logs": "/system/logs",
};

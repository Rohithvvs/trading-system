import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./hooks/useAuth";
import { ThemeProvider } from "./hooks/useTheme";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AppShell } from "./layout/AppShell";
import { startKeepAlive } from "./utils/keepAlive";
import "./styles.css";

const Login = lazy(() => import("./pages/Login").then((m) => ({ default: m.Login })));
const Signup = lazy(() => import("./pages/Signup").then((m) => ({ default: m.Signup })));
const ForgotPassword = lazy(() =>
  import("./pages/ForgotPassword").then((m) => ({ default: m.ForgotPassword })),
);
const ResetPassword = lazy(() =>
  import("./pages/ResetPassword").then((m) => ({ default: m.ResetPassword })),
);

const DashboardPage = lazy(() =>
  import("./pages/retail/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const WatchlistsPage = lazy(() =>
  import("./pages/retail/WatchlistsPage").then((m) => ({ default: m.WatchlistsPage })),
);
const QuoteBoardPage = lazy(() =>
  import("./pages/retail/QuoteBoardPage").then((m) => ({ default: m.QuoteBoardPage })),
);
const ChartWorkspacePage = lazy(() =>
  import("./pages/retail/ChartWorkspacePage").then((m) => ({ default: m.ChartWorkspacePage })),
);
const HoldingsPage = lazy(() =>
  import("./pages/retail/HoldingsPage").then((m) => ({ default: m.HoldingsPage })),
);
const PositionsPage = lazy(() =>
  import("./pages/retail/PositionsPage").then((m) => ({ default: m.PositionsPage })),
);
const OrdersPage = lazy(() =>
  import("./pages/retail/OrdersPage").then((m) => ({ default: m.OrdersPage })),
);
const OrderHistoryPage = lazy(() =>
  import("./pages/retail/OrderHistoryPage").then((m) => ({ default: m.OrderHistoryPage })),
);
const HeatmapPage = lazy(() =>
  import("./pages/retail/HeatmapPage").then((m) => ({ default: m.HeatmapPage })),
);
const NotificationsPage = lazy(() =>
  import("./pages/retail/NotificationsPage").then((m) => ({ default: m.NotificationsPage })),
);
const ScannerPage = lazy(() =>
  import("./pages/retail/ScannerPage").then((m) => ({ default: m.ScannerPage })),
);
const PaperTradingRoutePage = lazy(() =>
  import("./pages/retail/PaperTradingRoutePage").then((m) => ({ default: m.PaperTradingRoutePage })),
);
const PortfolioPage = lazy(() =>
  import("./pages/retail/PortfolioPage").then((m) => ({ default: m.PortfolioPage })),
);
const SettingsPage = lazy(() =>
  import("./pages/retail/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const ReportsPage = lazy(() =>
  import("./pages/retail/ReportsPage").then((m) => ({ default: m.ReportsPage })),
);
const TradeJournalPage = lazy(() =>
  import("./pages/retail/TradeJournalPage").then((m) => ({ default: m.TradeJournalPage })),
);
const UserProfilePage = lazy(() =>
  import("./components/profile/UserProfilePage").then((m) => ({ default: m.UserProfilePage })),
);
const SystemLogs = lazy(() => import("./pages/SystemLogs").then((m) => ({ default: m.SystemLogs })));
const CentralCommand = lazy(() =>
  import("./components/CentralCommand").then((m) => ({ default: m.CentralCommand })),
);

const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: false },
  },
});

function GoogleProviderLayer({ children }: { children: React.ReactNode }) {
  if (!googleClientId) {
    return <>{children}</>;
  }
  return <GoogleOAuthProvider clientId={googleClientId}>{children}</GoogleOAuthProvider>;
}

function AuthFallback() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--bg, #0e1116)",
        color: "var(--text-muted, #9eacbb)",
      }}
    >
      <div className="app-skel" style={{ width: 280, height: 320, borderRadius: 16 }} />
    </div>
  );
}

startKeepAlive();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <GoogleProviderLayer>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <AuthProvider>
            <BrowserRouter>
              <Suspense fallback={<AuthFallback />}>
                <Routes>
                  <Route path="/login" element={<Login />} />
                  <Route path="/signup" element={<Signup />} />
                  <Route path="/auth/forgot-password" element={<ForgotPassword />} />
                  <Route path="/auth/reset-password" element={<ResetPassword />} />

                  <Route
                    element={
                      <ProtectedRoute>
                        <AppShell />
                      </ProtectedRoute>
                    }
                  >
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<DashboardPage />} />
                    <Route path="/watchlists" element={<WatchlistsPage />} />
                    <Route path="/quotes" element={<QuoteBoardPage />} />
                    <Route path="/chart" element={<ChartWorkspacePage />} />
                    <Route path="/chart/:symbol" element={<ChartWorkspacePage />} />
                    <Route path="/holdings" element={<HoldingsPage />} />
                    <Route path="/positions" element={<PositionsPage />} />
                    <Route path="/orders" element={<OrdersPage />} />
                    <Route path="/order-history" element={<OrderHistoryPage />} />
                    <Route path="/heatmap" element={<HeatmapPage />} />
                    <Route path="/scanner" element={<ScannerPage />} />
                    <Route path="/alerts" element={<NotificationsPage />} />
                    <Route path="/paper-trading" element={<PaperTradingRoutePage />} />
                    <Route path="/portfolio" element={<PortfolioPage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route path="/reports" element={<ReportsPage />} />
                    <Route path="/trade-journal" element={<TradeJournalPage />} />
                    <Route
                      path="/profile"
                      element={
                        <UserProfilePage
                          onNavigate={(view) => {
                            if (view === "scanner") window.location.assign("/scanner");
                            else if (view === "paper-trading") window.location.assign("/paper-trading");
                            else window.location.assign("/dashboard");
                          }}
                        />
                      }
                    />
                    <Route path="/logs" element={<SystemLogs />} />
                    <Route path="/central-command" element={<CentralCommand />} />
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                  </Route>
                </Routes>
              </Suspense>
            </BrowserRouter>
          </AuthProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </GoogleProviderLayer>
  </React.StrictMode>,
);

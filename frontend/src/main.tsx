import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { GoogleOAuthProvider } from "@react-oauth/google";
import App from "./App";
import { AuthProvider } from "./hooks/useAuth";
import { ThemeProvider } from "./hooks/useTheme";
import { DensityProvider } from "./hooks/useDensity";
import { DeveloperModeProvider } from "./hooks/useDeveloperMode";
import { ToastProvider } from "./design-system";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { startKeepAlive } from "./utils/keepAlive";
import "./design-system/tokens.css";
import "./design-system/components.css";
import "./layout/shell.css";
import "./styles.css";

// Auth screens are rarely needed after login — lazy load them
const Login = lazy(() => import("./pages/Login").then((m) => ({ default: m.Login })));
const Signup = lazy(() => import("./pages/Signup").then((m) => ({ default: m.Signup })));
const ForgotPassword = lazy(() =>
  import("./pages/ForgotPassword").then((m) => ({ default: m.ForgotPassword })),
);
const ResetPassword = lazy(() =>
  import("./pages/ResetPassword").then((m) => ({ default: m.ResetPassword })),
);

const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

function GoogleProviderLayer({ children }: { children: React.ReactNode }) {
  if (!googleClientId) {
    return <>{children}</>;
  }
  return (
    <GoogleOAuthProvider clientId={googleClientId}>
      {children}
    </GoogleOAuthProvider>
  );
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

// Warm Render / health endpoint in background (never blocks UI)
startKeepAlive();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <GoogleProviderLayer>
      <ThemeProvider>
        <DensityProvider>
          <DeveloperModeProvider>
            <ToastProvider>
              <AuthProvider>
                <BrowserRouter>
                  <Suspense fallback={<AuthFallback />}>
                    <Routes>
                      <Route path="/login" element={<Login />} />
                      <Route path="/signup" element={<Signup />} />
                      <Route path="/auth/forgot-password" element={<ForgotPassword />} />
                      <Route path="/auth/reset-password" element={<ResetPassword />} />
                      {/* Authenticated app — full retail routing lives in App */}
                      <Route
                        path="*"
                        element={
                          <ProtectedRoute>
                            <App />
                          </ProtectedRoute>
                        }
                      />
                    </Routes>
                  </Suspense>
                </BrowserRouter>
              </AuthProvider>
            </ToastProvider>
          </DeveloperModeProvider>
        </DensityProvider>
      </ThemeProvider>
    </GoogleProviderLayer>
  </React.StrictMode>
);

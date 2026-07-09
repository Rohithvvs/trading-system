import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { GoogleOAuthProvider } from "@react-oauth/google";
import App from "./App";
import { Login } from "./pages/Login";
import { Signup } from "./pages/Signup";
import { AuthProvider } from "./hooks/useAuth";
import { ThemeProvider } from "./hooks/useTheme";
import { ProtectedRoute } from "./components/ProtectedRoute";
import "./styles.css";

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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <GoogleProviderLayer>
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/signup" element={<Signup />} />
              {/* Any other route falls into App, protected by ProtectedRoute */}
              <Route 
                path="*" 
                element={
                  <ProtectedRoute>
                    <App />
                  </ProtectedRoute>
                } 
              />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </GoogleProviderLayer>
  </React.StrictMode>
);

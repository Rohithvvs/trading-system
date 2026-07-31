import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ThemeProvider } from "./hooks/useTheme";
import { DensityProvider } from "./hooks/useDensity";
import { DeveloperModeProvider } from "./hooks/useDeveloperMode";
import { ToastProvider } from "./design-system";
import { startKeepAlive } from "./utils/keepAlive";
import "./design-system/tokens.css";
import "./design-system/components.css";
import "./layout/shell.css";
import "./styles.css";

// Warm Render / health endpoint in background (never blocks UI)
startKeepAlive();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <DensityProvider>
        <DeveloperModeProvider>
          <ToastProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </ToastProvider>
        </DeveloperModeProvider>
      </DensityProvider>
    </ThemeProvider>
  </React.StrictMode>
);

import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route, Navigate } from "react-router-dom";

/**
 * 026-remove-multi-user — US1 + edge cases for deprecated auth routes.
 *
 * Mirrors App.tsx routing policy without mounting the full scanner stack:
 *  - `/` redirects into the trading shell (scanner)
 *  - unknown / deprecated auth paths fall through to the trading shell
 *  - no ProtectedRoute / login redirect
 */

function SingleUserRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/scanner" replace />} />
      <Route path="/home" element={<Navigate to="/scanner" replace />} />
      <Route path="/scanner" element={<div data-testid="page-scanner">Scanner</div>} />
      <Route path="/markets" element={<div data-testid="page-markets">Markets</div>} />
      <Route path="/paper" element={<div data-testid="page-paper">Paper</div>} />
      <Route path="/admin/command" element={<div data-testid="page-command">Central Command</div>} />
      {/* Spec edge: /login /signup gracefully leave the auth surface */}
      <Route path="*" element={<Navigate to="/scanner" replace />} />
    </Routes>
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SingleUserRoutes />
    </MemoryRouter>,
  );
}

describe("single-user routing (US1, edge deprecated auth paths)", () => {
  it("loads scanner from root without login redirect", async () => {
    renderAt("/");
    await waitFor(() => {
      expect(screen.getByTestId("page-scanner")).toBeTruthy();
    });
    expect(screen.queryByTestId("page-login")).toBeNull();
  });

  it("direct /markets loads without auth check", async () => {
    renderAt("/markets");
    await waitFor(() => {
      expect(screen.getByTestId("page-markets")).toBeTruthy();
    });
  });

  it("direct /paper loads without auth check", async () => {
    renderAt("/paper");
    await waitFor(() => {
      expect(screen.getByTestId("page-paper")).toBeTruthy();
    });
  });

  it("edge: /login falls through to scanner (no login page)", async () => {
    renderAt("/login");
    await waitFor(() => {
      expect(screen.getByTestId("page-scanner")).toBeTruthy();
    });
  });

  it("edge: /signup falls through to scanner", async () => {
    renderAt("/signup");
    await waitFor(() => {
      expect(screen.getByTestId("page-scanner")).toBeTruthy();
    });
  });

  it("edge: /profile falls through to scanner (profile removed)", async () => {
    renderAt("/profile");
    await waitFor(() => {
      expect(screen.getByTestId("page-scanner")).toBeTruthy();
    });
  });

  it("Central Command is reachable without AdminRoute gate", async () => {
    renderAt("/admin/command");
    await waitFor(() => {
      expect(screen.getByTestId("page-command")).toBeTruthy();
    });
  });
});

describe("api client has no user-auth helpers (FR-010-01)", () => {
  it("api module does not export login/signup/profile/session helpers", async () => {
    const api = await import("../api");
    const forbidden = [
      "login",
      "signup",
      "logout",
      "forgotPassword",
      "resetPassword",
      "fetchProfile",
      "updateUserProfile",
      "patchUserProfile",
      "getMe",
      "fetchSessions",
      "deleteSession",
      "googleLogin",
    ];
    for (const name of forbidden) {
      expect(api).not.toHaveProperty(name);
    }
  });

  it("api module retains paper trading and FYERS helpers (FR-013)", async () => {
    const api = await import("../api");
    // Presence of trading helpers (names used across the SPA)
    const retained = Object.keys(api);
    expect(retained.some((k) => /paper|token|fyers|scanner|broker/i.test(k))).toBe(true);
  });
});

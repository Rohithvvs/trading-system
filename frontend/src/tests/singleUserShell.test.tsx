import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../layout/AppShell";
import { ThemeProvider } from "../hooks/useTheme";
import { DensityProvider } from "../hooks/useDensity";
import { DeveloperModeProvider } from "../hooks/useDeveloperMode";

/**
 * 026-remove-multi-user — US1 / US3
 * App shell launches without auth chrome (avatar, profile menu, logout).
 */

function installMatchMediaMock() {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

function renderShell(ui?: React.ReactNode) {
  return render(
    <MemoryRouter initialEntries={["/scanner"]}>
      <ThemeProvider>
        <DensityProvider>
          <DeveloperModeProvider>
            <AppShell>{ui ?? <div data-testid="shell-child">Dashboard</div>}</AppShell>
          </DeveloperModeProvider>
        </DensityProvider>
      </ThemeProvider>
    </MemoryRouter>,
  );
}

describe("AppShell single-user UI (US3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installMatchMediaMock();
    try {
      localStorage.clear();
    } catch {
      /* ignore */
    }
  });

  it("renders navigation without profile avatar, logout, or login controls", () => {
    renderShell();

    expect(screen.getByTestId("shell-child")).toBeTruthy();
    expect(screen.getByTestId("nav-markets")).toBeTruthy();
    expect(screen.getByTestId("nav-scanner")).toBeTruthy();
    expect(screen.getByTestId("nav-paper-trading")).toBeTruthy();

    // Profile / auth chrome must be absent
    expect(screen.queryByTestId("nav-profile")).toBeNull();
    expect(screen.queryByText(/log\s*out/i)).toBeNull();
    expect(screen.queryByText(/sign\s*up/i)).toBeNull();
    expect(screen.queryByText(/sign\s*in/i)).toBeNull();
    expect(screen.queryByText(/login/i)).toBeNull();
    expect(screen.queryByLabelText(/user menu|profile menu|account menu/i)).toBeNull();
  });

  it("exposes trading CTAs and density controls without user email (US3 acceptance)", () => {
    renderShell();

    expect(screen.getByTestId("global-buy-cta")).toBeTruthy();
    expect(screen.getByTestId("global-sell-cta")).toBeTruthy();
    expect(screen.getByLabelText(/ui density/i)).toBeTruthy();

    // No user email / owner@ personal badge in shell
    expect(screen.queryByText(/@/)).toBeNull();
  });

  it("renders child content immediately without auth gate (US1)", () => {
    renderShell(<div data-testid="central-command">Central Command</div>);
    expect(screen.getByTestId("central-command").textContent).toContain("Central Command");
    expect(screen.queryByText(/please log in|authenticate|session expired/i)).toBeNull();
  });
});

describe("removed auth page modules (SC-001)", () => {
  const removedPages = [
    "../pages/Login",
    "../pages/Signup",
    "../pages/ForgotPassword",
    "../pages/ResetPassword",
    "../pages/SettingsSessions",
    "../components/ProtectedRoute",
    "../components/AdminRoute",
    "../hooks/useAuth",
    "../api_auth",
    "../api_auth_login",
  ];

  it.each(removedPages)("module %s is not resolvable", async (mod) => {
    await expect(import(/* @vite-ignore */ mod)).rejects.toBeTruthy();
  });
});

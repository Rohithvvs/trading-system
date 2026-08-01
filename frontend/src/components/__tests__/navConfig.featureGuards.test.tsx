import { render, screen } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AppShell } from "../../layout/AppShell";
import { RETAIL_NAV, ADMIN_NAV, isNavActive } from "../../layout/navConfig";

const mockUseAuth = vi.fn();
const mockCanAccess = vi.fn();

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../../hooks/useTheme", () => ({
  useTheme: () => ({ theme: "dark", toggleTheme: vi.fn() }),
}));

vi.mock("../../hooks/useDensity", () => ({
  useDensity: () => ({ density: "comfortable", setDensity: vi.fn() }),
}));

vi.mock("../../hooks/useFeaturePermissions", () => ({
  useFeaturePermissions: () => ({
    canAccess: mockCanAccess,
    isLoading: false,
    permissions: {},
    error: null,
    refetchPermissions: vi.fn(),
  }),
}));

function renderShell() {
  return render(
    <MemoryRouter>
      <AppShell>
        <div>Page Content</div>
      </AppShell>
    </MemoryRouter>,
  );
}

describe("navConfig featureKey annotations (schema)", () => {
  it("annotates retail nav items with expected feature keys", () => {
    const byId = Object.fromEntries(RETAIL_NAV.map((n) => [n.id, n]));

    expect(byId.markets.featureKey).toBeUndefined(); // ungated core
    expect(byId.scanner.featureKey).toBe("advanced_scanner");
    expect(byId.performance.featureKey).toBe("portfolio_analytics");
    expect(byId.paper.featureKey).toBeUndefined();
    expect(byId.profile.featureKey).toBeUndefined();
  });

  it("annotates admin nav items with expected feature keys", () => {
    const byId = Object.fromEntries(ADMIN_NAV.map((n) => [n.id, n]));

    expect(byId["admin-panel"].featureKey).toBe("admin_panel");
    expect(byId["admin-command"].featureKey).toBe("central_command");
    expect(byId["admin-logs"].featureKey).toBe("system_logs");
    expect(byId["admin-diagnostics"].featureKey).toBeUndefined();
  });

  it("isNavActive matches path prefixes correctly for feature-gated routes", () => {
    const scanner = RETAIL_NAV.find((n) => n.id === "scanner")!;
    const performance = RETAIL_NAV.find((n) => n.id === "performance")!;
    const adminPanel = ADMIN_NAV.find((n) => n.id === "admin-panel")!;
    const logs = ADMIN_NAV.find((n) => n.id === "admin-logs")!;

    // location.pathname never includes query string; prefix match uses path only
    expect(isNavActive("/scanner", scanner)).toBe(true);
    expect(isNavActive("/scanner/detail", scanner)).toBe(true);
    expect(isNavActive("/performance", performance)).toBe(true);
    expect(isNavActive("/admin", adminPanel)).toBe(true);
    expect(isNavActive("/admin/logs", adminPanel)).toBe(false); // exact admin panel
    expect(isNavActive("/admin/logs", logs)).toBe(true);
  });
});

describe("AppShell Dynamic Navigation Filtering (Sprint 5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "matchMedia", {
      writable: true,
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
  });

  it("renders retail navigation links when feature access is granted", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "trader",
      user: { id: "1", email: "trader@example.com", full_name: "Trader User", role: "trader" },
    });
    mockCanAccess.mockReturnValue(true);

    renderShell();

    expect(screen.getByTestId("nav-markets")).toBeTruthy();
    expect(screen.getByTestId("nav-scanner")).toBeTruthy();
    expect(screen.getByTestId("nav-performance")).toBeTruthy();
    expect(screen.getByTestId("nav-paper-trading")).toBeTruthy();
    expect(screen.getByTestId("nav-profile")).toBeTruthy();
  });

  it("filters out navigation links when feature permission is denied", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "trader",
      user: { id: "1", email: "trader@example.com", full_name: "Trader User", role: "trader" },
    });

    mockCanAccess.mockImplementation((featureKey: string) => {
      if (featureKey === "advanced_scanner") return false;
      if (featureKey === "portfolio_analytics") return false;
      return true;
    });

    renderShell();

    expect(screen.getByTestId("nav-markets")).toBeTruthy();
    expect(screen.queryByTestId("nav-scanner")).toBeNull();
    expect(screen.queryByTestId("nav-performance")).toBeNull();
    // Ungated items remain
    expect(screen.getByTestId("nav-paper-trading")).toBeTruthy();
    expect(screen.getByTestId("nav-profile")).toBeTruthy();
  });

  it("AC-FEAT-05: hides Performance nav when portfolio_analytics is admin-only for trader", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "trader",
      user: { id: "1", email: "trader@example.com", full_name: "Trader User", role: "trader" },
    });

    mockCanAccess.mockImplementation((featureKey: string) => {
      if (featureKey === "portfolio_analytics") return false;
      return true;
    });

    renderShell();

    expect(screen.queryByTestId("nav-performance")).toBeNull();
    expect(screen.getByTestId("nav-markets")).toBeTruthy();
    expect(screen.getByTestId("nav-scanner")).toBeTruthy();
  });

  it("filters admin navigation items based on role and feature permissions", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "admin",
      user: { id: "2", email: "admin@example.com", full_name: "Admin User", role: "admin" },
    });

    mockCanAccess.mockImplementation((featureKey: string) => {
      if (featureKey === "central_command") return false;
      return true;
    });

    renderShell();

    expect(screen.getByTestId("nav-admin-panel")).toBeTruthy();
    expect(screen.getByTestId("nav-system-logs")).toBeTruthy();
    expect(screen.queryByTestId("nav-central-command")).toBeNull();
  });

  it("hides all feature-gated admin nav items when canAccess denies admin features", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "admin",
      user: { id: "2", email: "admin@example.com", full_name: "Admin User", role: "admin" },
    });

    mockCanAccess.mockImplementation((featureKey: string) => {
      if (["admin_panel", "central_command", "system_logs"].includes(featureKey)) return false;
      return true;
    });

    renderShell();

    expect(screen.queryByTestId("nav-admin-panel")).toBeNull();
    expect(screen.queryByTestId("nav-central-command")).toBeNull();
    expect(screen.queryByTestId("nav-system-logs")).toBeNull();
    // Diagnostics has no featureKey — still visible for admin role
    expect(screen.getByTestId("nav-diagnostics")).toBeTruthy();
  });

  it("trader role never receives admin nav items regardless of canAccess", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "trader",
      user: { id: "1", email: "trader@example.com", full_name: "Trader", role: "trader" },
    });
    // Even if canAccess wrongly returns true for admin keys, AppShell role filter applies first
    mockCanAccess.mockReturnValue(true);

    renderShell();

    expect(screen.queryByTestId("nav-admin-panel")).toBeNull();
    expect(screen.queryByTestId("nav-central-command")).toBeNull();
    expect(screen.queryByTestId("nav-system-logs")).toBeNull();
    expect(screen.queryByTestId("nav-diagnostics")).toBeNull();
  });

  it("does not call canAccess for nav items without featureKey", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "trader",
      user: { id: "1", email: "trader@example.com", full_name: "Trader", role: "trader" },
    });
    mockCanAccess.mockReturnValue(true);

    renderShell();

    const calledKeys = mockCanAccess.mock.calls.map((c) => c[0]);
    expect(calledKeys).not.toContain(undefined);
    expect(calledKeys).toContain("advanced_scanner");
    expect(calledKeys).toContain("portfolio_analytics");
    // markets / paper / profile have no featureKey
    expect(calledKeys).not.toContain("markets");
  });

  it("AC-FEAT-06 nav: fail-closed canAccess hides all gated nav links", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "admin",
      user: { id: "2", email: "admin@example.com", full_name: "Admin", role: "admin" },
    });
    // Simulate fail-closed: everything denied
    mockCanAccess.mockReturnValue(false);

    renderShell();

    expect(screen.getByTestId("nav-markets")).toBeTruthy(); // ungated
    expect(screen.getByTestId("nav-paper-trading")).toBeTruthy();
    expect(screen.getByTestId("nav-profile")).toBeTruthy();
    expect(screen.queryByTestId("nav-scanner")).toBeNull();
    expect(screen.queryByTestId("nav-performance")).toBeNull();
    expect(screen.queryByTestId("nav-admin-panel")).toBeNull();
    expect(screen.queryByTestId("nav-system-logs")).toBeNull();
    expect(screen.queryByTestId("nav-central-command")).toBeNull();
  });
});

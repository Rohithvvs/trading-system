/**
 * Sprint 4 AC matrix — maps each AC-* to at least one automated assertion.
 * Detailed flows live in AdminRoute / Users / Features / Panel tests.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AdminRoute } from "../AdminRoute";
import { AdminPanelPage } from "../admin/AdminPanelPage";
import { ToastProvider } from "../../design-system";
import { ADMIN_NAV, RETAIL_NAV } from "../../layout/navConfig";

const mockUseAuth = vi.fn();
vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../admin/UsersAdminTab", () => ({
  UsersAdminTab: () => <div data-testid="users-tab-body">Users</div>,
}));
vi.mock("../admin/FeaturesAdminTab", () => ({
  FeaturesAdminTab: () => <div data-testid="features-tab-body">Features</div>,
}));

describe("Sprint 4 AC matrix (access)", () => {
  beforeEach(() => mockUseAuth.mockReset());

  it("AC-ACC-01 unauthenticated → login", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      role: "trader",
      user: null,
    });
    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <div data-testid="admin-ok">OK</div>
              </AdminRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("login-page")).toBeTruthy();
  });

  it("AC-ACC-02 trader forbidden, no panel data", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "trader",
      user: { id: "1", email: "t@x.com", full_name: "T", role: "trader" },
    });
    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <div data-testid="secret-users">SECRET</div>
              </AdminRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("admin-forbidden")).toBeTruthy();
    expect(screen.queryByTestId("secret-users")).toBeNull();
  });

  it("AC-ACC-03 admin sees panel tabs", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "admin",
      user: { id: "1", email: "a@x.com", full_name: "A", role: "admin" },
    });
    render(
      <ToastProvider>
        <MemoryRouter initialEntries={["/admin"]}>
          <Routes>
            <Route
              path="/admin"
              element={
                <AdminRoute>
                  <AdminPanelPage />
                </AdminRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      </ToastProvider>,
    );
    expect(screen.getByTestId("admin-panel-page")).toBeTruthy();
    expect(screen.getByTestId("tab-users")).toBeTruthy();
    expect(screen.getByTestId("tab-features")).toBeTruthy();
  });

  it("AC-ACC-05/06 gate is role-only (no developerMode in AdminRoute)", () => {
    // Trader blocked even without any developerMode mock — component never reads it
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "trader",
      user: { id: "1", email: "t@x.com", full_name: "T", role: "trader" },
    });
    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <Routes>
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <div data-testid="admin-ok">OK</div>
              </AdminRoute>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("admin-forbidden")).toBeTruthy();
  });

  it("AC-ACC-04/REG-01 admin nav set has Admin; retail does not", () => {
    expect(ADMIN_NAV.some((i) => i.id === "admin-panel")).toBe(true);
    expect(RETAIL_NAV.some((i) => i.path === "/admin")).toBe(false);
  });

  it("AC-ACC-07 admin routes include logs and command paths in admin nav", () => {
    expect(ADMIN_NAV.some((i) => i.path === "/admin/logs")).toBe(true);
    expect(ADMIN_NAV.some((i) => i.path === "/admin/command")).toBe(true);
  });
});

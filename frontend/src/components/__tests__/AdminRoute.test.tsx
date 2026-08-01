import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AdminRoute } from "../AdminRoute";

const mockUseAuth = vi.fn();

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/admin"
          element={
            <AdminRoute>
              <div data-testid="admin-ok">Admin Content</div>
            </AdminRoute>
          }
        />
        <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        <Route path="/scanner" element={<div>Scanner</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AdminRoute (Sprint 4 role gate)", () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
  });

  it("allows admin role to see children", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "admin",
      user: { id: "1", email: "a@x.com", full_name: "A", role: "admin" },
    });
    renderAt("/admin");
    expect(screen.getByTestId("admin-ok")).toBeTruthy();
  });

  it("blocks trader with forbidden UI", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      role: "trader",
      user: { id: "2", email: "t@x.com", full_name: "T", role: "trader" },
    });
    renderAt("/admin");
    expect(screen.getByTestId("admin-forbidden")).toBeTruthy();
    expect(screen.queryByTestId("admin-ok")).toBeNull();
  });

  it("redirects unauthenticated users to login", () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      role: "trader",
      user: null,
    });
    renderAt("/admin");
    expect(screen.getByTestId("login-page")).toBeTruthy();
  });
});


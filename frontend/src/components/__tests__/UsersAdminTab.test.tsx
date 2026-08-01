import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { UsersAdminTab } from "../admin/UsersAdminTab";
import { ToastProvider } from "../../design-system";

const listAdminUsers = vi.fn();
const updateUserRole = vi.fn();
const mockLogout = vi.fn();

vi.mock("../../api_admin", async () => {
  const actual = await vi.importActual<typeof import("../../api_admin")>("../../api_admin");
  return {
    ...actual,
    listAdminUsers: (...args: unknown[]) => listAdminUsers(...args),
    updateUserRole: (...args: unknown[]) => updateUserRole(...args),
  };
});

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
    role: "admin",
    logout: mockLogout,
  }),
}));

function wrap(ui: React.ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

const sampleUser = {
  id: "u1",
  email: "trader@example.com",
  full_name: "T User",
  role: "trader" as const,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

describe("UsersAdminTab", () => {
  beforeEach(() => {
    listAdminUsers.mockReset();
    updateUserRole.mockReset();
    mockLogout.mockReset();
    listAdminUsers.mockResolvedValue({
      items: [sampleUser],
      total: 1,
      page: 1,
      size: 20,
    });
  });

  it("renders users from API", async () => {
    wrap(<UsersAdminTab />);
    await waitFor(() => {
      expect(screen.getByText("trader@example.com")).toBeTruthy();
    });
    expect(listAdminUsers).toHaveBeenCalled();
  });


  it("promotes user after confirm", async () => {
    updateUserRole.mockResolvedValue({ ...sampleUser, role: "admin" });
    wrap(<UsersAdminTab />);
    await waitFor(() => screen.getByText("trader@example.com"));
    fireEvent.click(screen.getByTestId("promote-u1"));
    fireEvent.click(screen.getByRole("button", { name: /Promote to admin/i }));
    await waitFor(() => {
      expect(updateUserRole).toHaveBeenCalledWith("u1", "admin");
    });
  });

  it("shows error on last-admin 400 without changing role", async () => {
    const { AdminApiError } = await import("../../api_admin");
    updateUserRole.mockRejectedValue(
      new AdminApiError(400, "Cannot demote the last active admin"),
    );
    listAdminUsers.mockResolvedValue({
      items: [{ ...sampleUser, id: "a1", email: "admin@example.com", role: "admin" }],
      total: 1,
      page: 1,
      size: 20,
    });
    wrap(<UsersAdminTab />);
    await waitFor(() => screen.getByText("admin@example.com"));
    fireEvent.click(screen.getByTestId("demote-a1"));
    fireEvent.click(screen.getByRole("button", { name: /Demote to trader/i }));
    await waitFor(() => {
      expect(updateUserRole).toHaveBeenCalled();
    });
    expect(screen.getByText("admin@example.com")).toBeTruthy();
    // still admin badge present
    expect(screen.getByText("admin")).toBeTruthy();
  });

  it("sends search query to listAdminUsers (AC-USR-08)", async () => {
    wrap(<UsersAdminTab />);
    await waitFor(() => screen.getByTestId("users-search"));
    fireEvent.change(screen.getByTestId("users-search"), {
      target: { value: "alice" },
    });
    await waitFor(
      () => {
        expect(listAdminUsers).toHaveBeenCalledWith(
          expect.objectContaining({ search: "alice", page: 1 }),
        );
      },
      { timeout: 1500 },
    );
  });

  it("shows empty state when API returns no items (AC-USR-06)", async () => {
    listAdminUsers.mockResolvedValue({ items: [], total: 0, page: 1, size: 20 });
    wrap(<UsersAdminTab />);
    await waitFor(() => {
      expect(screen.getByText(/No users found/i)).toBeTruthy();
    });
  });

  it("logs out on 403 authz failure (hardening M-2 / AC-USR-07)", async () => {
    const { AdminApiError } = await import("../../api_admin");
    listAdminUsers.mockRejectedValue(new AdminApiError(403, "Admin privileges required"));
    wrap(<UsersAdminTab />);
    await waitFor(() => {
      expect(mockLogout).toHaveBeenCalled();
    });
  });

  it("shows list error with retry on non-authz failure (AC-USR-07)", async () => {
    const { AdminApiError } = await import("../../api_admin");
    listAdminUsers.mockRejectedValue(new AdminApiError(500, "Internal server error"));
    wrap(<UsersAdminTab />);
    await waitFor(() => {
      expect(screen.getByText(/Internal server error/i)).toBeTruthy();
    });
    expect(screen.getByRole("button", { name: /Retry/i })).toBeTruthy();
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it("opens confirmation before role change (AC-USR-03)", async () => {
    wrap(<UsersAdminTab />);
    await waitFor(() => screen.getByTestId("promote-u1"));
    fireEvent.click(screen.getByTestId("promote-u1"));
    expect(screen.getByRole("button", { name: /Promote to admin/i })).toBeTruthy();
    expect(updateUserRole).not.toHaveBeenCalled();
  });
});



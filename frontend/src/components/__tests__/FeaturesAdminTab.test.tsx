import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { FeaturesAdminTab } from "../admin/FeaturesAdminTab";
import { ToastProvider } from "../../design-system";

const listAdminFeatures = vi.fn();
const updateFeaturePermission = vi.fn();
const mockLogout = vi.fn();

vi.mock("../../api_admin", async () => {
  const actual = await vi.importActual<typeof import("../../api_admin")>("../../api_admin");
  return {
    ...actual,
    listAdminFeatures: (...args: unknown[]) => listAdminFeatures(...args),
    updateFeaturePermission: (...args: unknown[]) => updateFeaturePermission(...args),
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

describe("FeaturesAdminTab", () => {
  beforeEach(() => {
    listAdminFeatures.mockReset();
    updateFeaturePermission.mockReset();
    mockLogout.mockReset();
    listAdminFeatures.mockResolvedValue({
      items: [
        {
          id: "1",
          feature_key: "watchlist",
          description: "Watchlist",
          allowed_roles: ["trader", "admin"],
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          id: "2",
          feature_key: "admin_panel",
          description: "Admin console",
          allowed_roles: ["admin"],
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
  });

  it("renders features from API", async () => {
    wrap(<FeaturesAdminTab />);
    await waitFor(() => {
      expect(screen.getByText("watchlist")).toBeTruthy();
    });
    expect(screen.getByText("admin_panel")).toBeTruthy();
  });


  it("saves allowed_roles only", async () => {
    updateFeaturePermission.mockResolvedValue({
      id: "1",
      feature_key: "watchlist",
      description: "Watchlist",
      allowed_roles: ["admin"],
      is_active: true,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });
    wrap(<FeaturesAdminTab />);
    await waitFor(() => screen.getByTestId("feat-trader-watchlist"));
    fireEvent.click(screen.getByTestId("feat-trader-watchlist")); // uncheck trader
    fireEvent.click(screen.getByTestId("feat-save-watchlist"));
    await waitFor(() => {
      expect(updateFeaturePermission).toHaveBeenCalledWith("watchlist", {
        allowed_roles: ["admin"],
      });
    });
  });

  it("locks admin checkbox on critical feature (AC-FEAT-07)", async () => {
    wrap(<FeaturesAdminTab />);
    await waitFor(() => screen.getByTestId("feat-admin-admin_panel"));
    expect((screen.getByTestId("feat-admin-admin_panel") as HTMLInputElement).disabled).toBe(true);
  });

  it("shows is_active as text not a toggle (AC-FEAT-06)", async () => {
    wrap(<FeaturesAdminTab />);
    await waitFor(() => screen.getByText("watchlist"));
    expect(screen.getAllByText(/Active status is read-only/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("checkbox", { name: /active/i })).toBeNull();
  });


  it("reverts roles on critical 400 (AC-FEAT-04)", async () => {
    const { AdminApiError } = await import("../../api_admin");
    updateFeaturePermission.mockRejectedValue(
      new AdminApiError(400, "Cannot remove admin from critical feature"),
    );
    wrap(<FeaturesAdminTab />);
    await waitFor(() => screen.getByTestId("feat-trader-admin_panel"));
    // admin is locked; toggle trader on critical and try save with only admin still
    fireEvent.click(screen.getByTestId("feat-trader-admin_panel"));
    fireEvent.click(screen.getByTestId("feat-save-admin_panel"));
    await waitFor(() => {
      expect(updateFeaturePermission).toHaveBeenCalled();
    });
    // after error, draft restored — admin still checked
    expect((screen.getByTestId("feat-admin-admin_panel") as HTMLInputElement).checked).toBe(true);
  });

  it("shows load error state (AC-FEAT-05)", async () => {
    const { AdminApiError } = await import("../../api_admin");
    listAdminFeatures.mockRejectedValue(new AdminApiError(500, "Server error"));
    wrap(<FeaturesAdminTab />);
    await waitFor(() => {
      expect(screen.getByText(/Server error/i)).toBeTruthy();
    });
  });
});



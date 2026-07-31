import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { WatchlistTab } from "../WatchlistTab";

const mockCanAccess = vi.fn();
let mockIsLoading = false;

vi.mock("../../hooks/useFeaturePermissions", () => ({
  useFeaturePermissions: () => ({
    canAccess: mockCanAccess,
    isLoading: mockIsLoading,
    permissions: {},
    error: null,
    refetchPermissions: vi.fn(),
  }),
}));

vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: { id: "1", email: "t@x.com", full_name: "Trader", role: "trader" },
  }),
}));

vi.mock("../../api", () => ({
  fetchUserProfile: vi.fn().mockResolvedValue({ preferences: { watchlist: [] } }),
  patchUserProfile: vi.fn(),
}));

vi.mock("../../design-system", async () => {
  const actual = await vi.importActual<typeof import("../../design-system")>("../../design-system");
  return {
    ...actual,
    useToast: () => ({
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    }),
  };
});

describe("WatchlistTab feature guard (Sprint 5 FR-006)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLoading = false;
  });

  it("renders watchlist content when watchlist feature access is granted", async () => {
    mockCanAccess.mockImplementation((key: string) => key === "watchlist");

    render(
      <MemoryRouter>
        <WatchlistTab />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("watchlist-tab-content")).toBeTruthy();
    });
    expect(screen.getByText("Watchlist")).toBeTruthy();
    expect(screen.queryByTestId("access-denied-view")).toBeNull();
    expect(mockCanAccess).toHaveBeenCalledWith("watchlist");
  });

  it("shows AccessDenied and does not render watchlist content when access denied", () => {
    mockCanAccess.mockReturnValue(false);

    render(
      <MemoryRouter>
        <WatchlistTab />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("access-denied-view")).toBeTruthy();
    expect(screen.queryByTestId("watchlist-tab-content")).toBeNull();
    expect(screen.queryByText("No watchlist")).toBeNull();
  });
});

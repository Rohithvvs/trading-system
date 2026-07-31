/**
 * Integration-style route protection tests for Sprint 5 feature surfaces.
 * Verifies FeatureGuard + AccessDenied wiring for each gated route key.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { FeatureGuard } from "../FeatureGuard";
import { AccessDenied } from "../AccessDenied";

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

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="current-path">{location.pathname}</div>;
}

/** Mirrors App.tsx route protection matrix for the six target features. */
function ProtectedAppRoutes() {
  return (
    <Routes>
      <Route path="/markets" element={<div data-testid="markets-page">Markets</div>} />
      <Route
        path="/scanner"
        element={
          <FeatureGuard feature="advanced_scanner" fallback={<AccessDenied />}>
            <div data-testid="scanner-page">Scanner</div>
          </FeatureGuard>
        }
      />
      <Route
        path="/performance"
        element={
          <FeatureGuard feature="portfolio_analytics" fallback={<AccessDenied />}>
            <div data-testid="performance-page">Performance</div>
          </FeatureGuard>
        }
      />
      <Route
        path="/admin/logs"
        element={
          <FeatureGuard feature="system_logs" fallback={<AccessDenied />}>
            <div data-testid="logs-page">System Logs</div>
          </FeatureGuard>
        }
      />
      <Route
        path="/admin/command"
        element={
          <FeatureGuard feature="central_command" fallback={<AccessDenied />}>
            <div data-testid="command-page">Central Command</div>
          </FeatureGuard>
        }
      />
      <Route
        path="/export-demo"
        element={
          <FeatureGuard feature="export_data">
            <button type="button" data-testid="export-data-btn">
              Export
            </button>
          </FeatureGuard>
        }
      />
      <Route
        path="/watchlist-demo"
        element={
          <FeatureGuard feature="watchlist" fallback={<AccessDenied />}>
            <div data-testid="watchlist-page">Watchlist</div>
          </FeatureGuard>
        }
      />
      <Route
        path="/paper/watchlist"
        element={
          <FeatureGuard feature="watchlist" fallback={<AccessDenied />}>
            <div data-testid="paper-watchlist-panel">Paper Watchlist Panel</div>
          </FeatureGuard>
        }
      />
    </Routes>
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <LocationDisplay />
      <ProtectedAppRoutes />
    </MemoryRouter>,
  );
}

describe("Feature route protection matrix (Sprint 5)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLoading = false;
  });

  const gatedRoutes: Array<{
    path: string;
    feature: string;
    pageTestId: string;
  }> = [
    { path: "/scanner", feature: "advanced_scanner", pageTestId: "scanner-page" },
    { path: "/performance", feature: "portfolio_analytics", pageTestId: "performance-page" },
    { path: "/admin/logs", feature: "system_logs", pageTestId: "logs-page" },
    { path: "/admin/command", feature: "central_command", pageTestId: "command-page" },
    { path: "/watchlist-demo", feature: "watchlist", pageTestId: "watchlist-page" },
    { path: "/paper/watchlist", feature: "watchlist", pageTestId: "paper-watchlist-panel" },
  ];

  it.each(gatedRoutes)(
    "denies direct URL access to $path when $feature is restricted",
    ({ path, feature, pageTestId }) => {
      mockCanAccess.mockImplementation((key: string) => key !== feature);

      renderAt(path);

      expect(screen.queryByTestId(pageTestId)).toBeNull();
      expect(screen.getByTestId("access-denied-view")).toBeTruthy();
      expect(mockCanAccess).toHaveBeenCalledWith(feature);
    },
  );

  it.each(gatedRoutes)(
    "allows $path when $feature access is granted",
    ({ path, feature, pageTestId }) => {
      mockCanAccess.mockReturnValue(true);

      renderAt(path);

      expect(screen.getByTestId(pageTestId)).toBeTruthy();
      expect(screen.queryByTestId("access-denied-view")).toBeNull();
      expect(mockCanAccess).toHaveBeenCalledWith(feature);
    },
  );

  it("export_data inline control is omitted from DOM when denied", () => {
    mockCanAccess.mockReturnValue(false);
    renderAt("/export-demo");
    expect(screen.queryByTestId("export-data-btn")).toBeNull();
  });

  it("export_data inline control renders when granted", () => {
    mockCanAccess.mockReturnValue(true);
    renderAt("/export-demo");
    expect(screen.getByTestId("export-data-btn")).toBeTruthy();
  });

  it("AccessDenied from restricted /scanner navigates back to /markets", () => {
    mockCanAccess.mockReturnValue(false);
    renderAt("/scanner");

    fireEvent.click(screen.getByTestId("access-denied-return-btn"));
    expect(screen.getByTestId("markets-page")).toBeTruthy();
    expect(screen.getByTestId("current-path").textContent).toBe("/markets");
  });

  it("shows loading fallback and never leaks protected page content while loading", () => {
    mockIsLoading = true;
    mockCanAccess.mockReturnValue(true);

    render(
      <MemoryRouter initialEntries={["/scanner"]}>
        <FeatureGuard
          feature="advanced_scanner"
          fallback={<AccessDenied />}
          loadingFallback={<div data-testid="perm-loading">Resolving permissions…</div>}
        >
          <div data-testid="scanner-page">Scanner</div>
        </FeatureGuard>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("perm-loading")).toBeTruthy();
    expect(screen.queryByTestId("scanner-page")).toBeNull();
    expect(screen.queryByTestId("access-denied-view")).toBeNull();
  });
});

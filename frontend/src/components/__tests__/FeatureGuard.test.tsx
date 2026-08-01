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

describe("FeatureGuard Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLoading = false;
  });

  // ── AC-FEAT-02: Access granted ────────────────────────────────────────────

  it("AC-FEAT-02: renders children when canAccess returns true (watchlist)", () => {
    mockCanAccess.mockReturnValue(true);

    render(
      <FeatureGuard feature="watchlist">
        <div data-testid="protected-content">Watchlist Content</div>
      </FeatureGuard>,
    );

    expect(screen.getByTestId("protected-content")).toBeTruthy();
    expect(screen.getByText("Watchlist Content")).toBeTruthy();
    expect(mockCanAccess).toHaveBeenCalledWith("watchlist");
  });

  // ── AC-FEAT-03: Access denied (inline) ────────────────────────────────────

  it("AC-FEAT-03: does not render children when canAccess returns false (export_data)", () => {
    mockCanAccess.mockReturnValue(false);

    render(
      <FeatureGuard feature="export_data">
        <div data-testid="protected-content">Export Content</div>
      </FeatureGuard>,
    );

    expect(screen.queryByTestId("protected-content")).toBeNull();
    expect(screen.queryByText("Export Content")).toBeNull();
    expect(mockCanAccess).toHaveBeenCalledWith("export_data");
  });

  it("renders custom fallback when canAccess returns false", () => {
    mockCanAccess.mockReturnValue(false);

    render(
      <FeatureGuard
        feature="advanced_scanner"
        fallback={<div data-testid="custom-fallback">Access Denied Fallback</div>}
      >
        <div data-testid="protected-content">Scanner Content</div>
      </FeatureGuard>,
    );

    expect(screen.queryByTestId("protected-content")).toBeNull();
    expect(screen.getByTestId("custom-fallback")).toBeTruthy();
  });

  it("renders null by default when denied and no fallback is provided (no DOM leakage)", () => {
    mockCanAccess.mockReturnValue(false);
    const { container } = render(
      <FeatureGuard feature="export_data">
        <button type="button" data-testid="export-btn">
          Export
        </button>
      </FeatureGuard>,
    );

    expect(screen.queryByTestId("export-btn")).toBeNull();
    expect(container.querySelector("[data-testid='export-btn']")).toBeNull();
  });

  // ── Loading state ─────────────────────────────────────────────────────────

  it("renders loadingFallback while permissions are loading", () => {
    mockIsLoading = true;
    mockCanAccess.mockReturnValue(true);

    render(
      <FeatureGuard
        feature="watchlist"
        loadingFallback={<div data-testid="loading-skeleton">Loading...</div>}
      >
        <div data-testid="protected-content">Watchlist Content</div>
      </FeatureGuard>,
    );

    expect(screen.getByTestId("loading-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("protected-content")).toBeNull();
    // Must not evaluate access until loading completes (or may call but children stay hidden)
  });

  it("does not render children while loading even if canAccess would return true", () => {
    mockIsLoading = true;
    mockCanAccess.mockReturnValue(true);

    render(
      <FeatureGuard feature="watchlist">
        <div data-testid="protected-content">Secret</div>
      </FeatureGuard>,
    );

    expect(screen.queryByTestId("protected-content")).toBeNull();
    // Default loading shell (audit M-3)
    expect(screen.getByTestId("feature-guard-loading")).toBeTruthy();
  });

  it("renders nothing while loading when loadingFallback is explicitly null", () => {
    mockIsLoading = true;
    mockCanAccess.mockReturnValue(true);

    render(
      <FeatureGuard feature="export_data" loadingFallback={null}>
        <button type="button" data-testid="export-btn">
          Export
        </button>
      </FeatureGuard>,
    );

    expect(screen.queryByTestId("export-btn")).toBeNull();
    expect(screen.queryByTestId("feature-guard-loading")).toBeNull();
  });

  it("does not render children while loading when access would be denied", () => {
    mockIsLoading = true;
    mockCanAccess.mockReturnValue(false);

    render(
      <FeatureGuard
        feature="system_logs"
        fallback={<div data-testid="denied">Denied</div>}
        loadingFallback={<div data-testid="loading">Loading</div>}
      >
        <div data-testid="protected-content">Logs</div>
      </FeatureGuard>,
    );

    expect(screen.getByTestId("loading")).toBeTruthy();
    expect(screen.queryByTestId("denied")).toBeNull();
    expect(screen.queryByTestId("protected-content")).toBeNull();
  });

  // ── AC-FEAT-04: Route-level AccessDenied ──────────────────────────────────

  it("AC-FEAT-04: renders AccessDenied as route-level fallback when feature denied", () => {
    mockCanAccess.mockReturnValue(false);

    render(
      <MemoryRouter initialEntries={["/scanner"]}>
        <Routes>
          <Route
            path="/scanner"
            element={
              <FeatureGuard feature="advanced_scanner" fallback={<AccessDenied />}>
                <div data-testid="scanner-page">Scanner Page</div>
              </FeatureGuard>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("scanner-page")).toBeNull();
    expect(screen.getByTestId("access-denied-view")).toBeTruthy();
    expect(screen.getByText("Access Denied")).toBeTruthy();
    expect(screen.getByTestId("access-denied-return-btn")).toBeTruthy();
  });

  it("AC-FEAT-04: AccessDenied return button navigates to /markets", () => {
    mockCanAccess.mockReturnValue(false);

    render(
      <MemoryRouter initialEntries={["/performance"]}>
        <LocationDisplay />
        <Routes>
          <Route
            path="/performance"
            element={
              <FeatureGuard feature="portfolio_analytics" fallback={<AccessDenied />}>
                <div data-testid="perf-page">Performance</div>
              </FeatureGuard>
            }
          />
          <Route path="/markets" element={<div data-testid="markets-page">Markets</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("access-denied-view")).toBeTruthy();
    fireEvent.click(screen.getByTestId("access-denied-return-btn"));
    expect(screen.getByTestId("markets-page")).toBeTruthy();
    expect(screen.getByTestId("current-path").textContent).toBe("/markets");
  });

  it("renders protected route children when feature access is granted", () => {
    mockCanAccess.mockReturnValue(true);

    render(
      <MemoryRouter initialEntries={["/scanner"]}>
        <Routes>
          <Route
            path="/scanner"
            element={
              <FeatureGuard feature="advanced_scanner" fallback={<AccessDenied />}>
                <div data-testid="scanner-page">Scanner Page</div>
              </FeatureGuard>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("scanner-page")).toBeTruthy();
    expect(screen.queryByTestId("access-denied-view")).toBeNull();
  });

  it("protects system_logs and central_command route surfaces with AccessDenied", () => {
    mockCanAccess.mockImplementation((key: string) => key !== "system_logs" && key !== "central_command");

    const { rerender } = render(
      <MemoryRouter initialEntries={["/admin/logs"]}>
        <FeatureGuard feature="system_logs" fallback={<AccessDenied />}>
          <div data-testid="logs-page">Logs</div>
        </FeatureGuard>
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("logs-page")).toBeNull();
    expect(screen.getByTestId("access-denied-view")).toBeTruthy();

    mockCanAccess.mockReturnValue(false);
    rerender(
      <MemoryRouter initialEntries={["/admin/command"]}>
        <FeatureGuard feature="central_command" fallback={<AccessDenied />}>
          <div data-testid="command-page">Command</div>
        </FeatureGuard>
      </MemoryRouter>,
    );

    expect(screen.queryByTestId("command-page")).toBeNull();
    expect(screen.getByTestId("access-denied-view")).toBeTruthy();
  });
});

describe("AccessDenied Component", () => {
  it("renders AccessDenied screen with default title, message, and return button", () => {
    render(
      <MemoryRouter>
        <AccessDenied />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("access-denied-view")).toBeTruthy();
    expect(screen.getByText("Access Denied")).toBeTruthy();
    expect(
      screen.getByText("You do not have permission to view or access this feature."),
    ).toBeTruthy();
    expect(screen.getByTestId("access-denied-return-btn")).toBeTruthy();
    expect(screen.getByText("Back to Markets")).toBeTruthy();
  });

  it("supports custom title, message, and returnPath", () => {
    render(
      <MemoryRouter initialEntries={["/blocked"]}>
        <LocationDisplay />
        <Routes>
          <Route
            path="/blocked"
            element={
              <AccessDenied
                title="Feature Disabled"
                message="This feature is currently turned off."
                returnPath="/scanner"
              />
            }
          />
          <Route path="/scanner" element={<div data-testid="scanner-home">Scanner</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Feature Disabled")).toBeTruthy();
    expect(screen.getByText("This feature is currently turned off.")).toBeTruthy();

    fireEvent.click(screen.getByTestId("access-denied-return-btn"));
    expect(screen.getByTestId("scanner-home")).toBeTruthy();
  });
});

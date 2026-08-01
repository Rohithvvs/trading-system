import { renderHook, waitFor, act } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { FeaturePermissionsProvider } from "../../contexts/FeaturePermissionsContext";
import { useFeaturePermissions } from "../useFeaturePermissions";
import * as apiAdmin from "../../api_admin";

const mockUseAuth = vi.fn();
const mockToastWarning = vi.fn();

vi.mock("../useAuth", () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock("../../design-system", async () => {
  const actual = await vi.importActual<typeof import("../../design-system")>("../../design-system");
  return {
    ...actual,
    useToast: () => ({
      toast: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      warning: mockToastWarning,
      info: vi.fn(),
      toasts: [],
    }),
  };
});

function adminAuth() {
  return {
    isAuthenticated: true,
    isLoading: false,
    role: "admin" as const,
    user: { id: "1", email: "admin@example.com", full_name: "Admin", role: "admin" as const },
  };
}

function traderAuth() {
  return {
    isAuthenticated: true,
    isLoading: false,
    role: "trader" as const,
    user: { id: "2", email: "trader@example.com", full_name: "Trader", role: "trader" as const },
  };
}

function makeFeature(
  feature_key: string,
  overrides: Partial<{
    allowed_roles: string[];
    is_active: boolean;
    description: string;
  }> = {},
) {
  return {
    id: `id-${feature_key}`,
    feature_key,
    description: overrides.description ?? feature_key,
    allowed_roles: overrides.allowed_roles ?? ["admin"],
    is_active: overrides.is_active ?? true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

describe("useFeaturePermissions hook & canAccess helper", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
    <FeaturePermissionsProvider>{children}</FeaturePermissionsProvider>
  );

  // ── Outside provider (H-3 deny-all) ───────────────────────────────────────

  it("fails closed outside FeaturePermissionsProvider (deny-all)", () => {
    const { result } = renderHook(() => useFeaturePermissions());
    expect(result.current.canAccess("watchlist")).toBe(false);
    expect(result.current.canAccess("export_data")).toBe(false);
    expect(result.current.canAccess("admin_panel")).toBe(false);
    expect(result.current.permissions).toEqual({});
    expect(result.current.isLoading).toBe(false);
  });

  // ── AC-FEAT-01: DB-backed session catalog ─────────────────────────────────

  it("fetches session features for admin and evaluates canAccess correctly", async () => {
    mockUseAuth.mockReturnValue(adminAuth());

    vi.spyOn(apiAdmin, "listSessionFeatures").mockResolvedValue({
      items: [
        makeFeature("watchlist", { allowed_roles: ["trader", "admin"] }),
        makeFeature("system_logs", { allowed_roles: ["admin"] }),
        makeFeature("export_data", { allowed_roles: ["admin"], is_active: false }),
      ],
    });

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.canAccess("watchlist")).toBe(true);
    expect(result.current.canAccess("system_logs")).toBe(true);
    expect(result.current.canAccess("export_data")).toBe(false);
    expect(result.current.canAccess("unknown_key")).toBe(false);
  });

  it("AC-FEAT-01: caches permissions and does not re-fetch on re-render", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    const listSpy = vi.spyOn(apiAdmin, "listSessionFeatures").mockResolvedValue({
      items: [makeFeature("watchlist", { allowed_roles: ["trader", "admin"] })],
    });

    const { result, rerender } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(listSpy).toHaveBeenCalledTimes(1);
    rerender();
    rerender();
    expect(listSpy).toHaveBeenCalledTimes(1);
  });

  // ── AC-FEAT-05: trader receives DB policy ─────────────────────────────────

  it("AC-FEAT-05: trader uses DB catalog so portfolio_analytics can be admin-only", async () => {
    mockUseAuth.mockReturnValue(traderAuth());
    vi.spyOn(apiAdmin, "listSessionFeatures").mockResolvedValue({
      items: [
        makeFeature("watchlist", { allowed_roles: ["trader", "admin"] }),
        makeFeature("advanced_scanner", { allowed_roles: ["trader", "admin"] }),
        makeFeature("portfolio_analytics", { allowed_roles: ["admin"] }),
        makeFeature("export_data", { allowed_roles: ["admin"] }),
      ],
    });

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.canAccess("watchlist")).toBe(true);
    expect(result.current.canAccess("advanced_scanner")).toBe(true);
    expect(result.current.canAccess("portfolio_analytics")).toBe(false);
    expect(result.current.canAccess("export_data")).toBe(false);
  });

  it("trader with default seed roles still gets retail surfaces from session API", async () => {
    mockUseAuth.mockReturnValue(traderAuth());
    vi.spyOn(apiAdmin, "listSessionFeatures").mockResolvedValue({
      items: [
        makeFeature("watchlist", { allowed_roles: ["trader", "admin"] }),
        makeFeature("advanced_scanner", { allowed_roles: ["trader", "admin"] }),
        makeFeature("portfolio_analytics", { allowed_roles: ["trader", "admin"] }),
        makeFeature("export_data", { allowed_roles: ["admin"] }),
        makeFeature("system_logs", { allowed_roles: ["admin"] }),
        makeFeature("central_command", { allowed_roles: ["admin"] }),
      ],
    });

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.canAccess("watchlist")).toBe(true);
    expect(result.current.canAccess("export_data")).toBe(false);
    expect(result.current.canAccess("system_logs")).toBe(false);
  });

  // ── 403-only trader catalog fallback ──────────────────────────────────────

  it("applies default catalog only on HTTP 403 for traders", async () => {
    mockUseAuth.mockReturnValue(traderAuth());
    vi.spyOn(apiAdmin, "listSessionFeatures").mockRejectedValue(
      new apiAdmin.AdminApiError(403, "Forbidden"),
    );

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.canAccess("watchlist")).toBe(true);
    expect(result.current.canAccess("export_data")).toBe(false);
  });

  // ── AC-FEAT-06: fail-closed for all roles on unresolvable errors ──────────

  it("AC-FEAT-06: fails closed when admin session features return HTTP 500", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    vi.spyOn(apiAdmin, "listSessionFeatures").mockRejectedValue(
      new apiAdmin.AdminApiError(500, "Internal Server Error"),
    );

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.permissions).toEqual({});
    expect(result.current.canAccess("watchlist")).toBe(false);
    expect(result.current.canAccess("system_logs")).toBe(false);
    expect(mockToastWarning).toHaveBeenCalled();
  });

  it("AC-FEAT-06: fails closed for trader on network error (not catalog fallback)", async () => {
    mockUseAuth.mockReturnValue(traderAuth());
    vi.spyOn(apiAdmin, "listSessionFeatures").mockRejectedValue(new Error("Network Error"));

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).not.toBeNull();
    expect(result.current.canAccess("watchlist")).toBe(false);
    expect(result.current.canAccess("advanced_scanner")).toBe(false);
    expect(result.current.canAccess("portfolio_analytics")).toBe(false);
    expect(mockToastWarning).toHaveBeenCalled();
  });

  it("fails closed for admin on HTTP 403 (no trader catalog)", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    vi.spyOn(apiAdmin, "listSessionFeatures").mockRejectedValue(
      new apiAdmin.AdminApiError(403, "Forbidden"),
    );

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.canAccess("watchlist")).toBe(false);
    expect(result.current.canAccess("system_logs")).toBe(false);
  });

  // ── M-1 invalid payload ───────────────────────────────────────────────────

  it("fails closed when API returns non-array items payload", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    vi.spyOn(apiAdmin, "listSessionFeatures").mockResolvedValue({
      items: null as unknown as [],
    });

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.canAccess("admin_panel")).toBe(false);
    expect(result.current.canAccess("watchlist")).toBe(false);
    expect(result.current.error).not.toBeNull();
  });

  // ── Unauthenticated ───────────────────────────────────────────────────────

  it("fails closed when user is unauthenticated", async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      isLoading: false,
      role: "trader",
      user: null,
    });

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.canAccess("watchlist")).toBe(false);
    expect(apiAdmin.listSessionFeatures).not.toHaveBeenCalled();
  });

  it("canAccess returns false for empty key and inactive features", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    vi.spyOn(apiAdmin, "listSessionFeatures").mockResolvedValue({
      items: [makeFeature("system_logs", { allowed_roles: ["admin"], is_active: false })],
    });

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.canAccess("")).toBe(false);
    expect(result.current.canAccess("system_logs")).toBe(false);
  });

  it("refetchPermissions revalidates after policy change", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    const listSpy = vi.spyOn(apiAdmin, "listSessionFeatures");

    listSpy.mockResolvedValueOnce({
      items: [makeFeature("export_data", { allowed_roles: ["admin"], is_active: true })],
    });

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.canAccess("export_data")).toBe(true);

    listSpy.mockResolvedValueOnce({
      items: [makeFeature("export_data", { allowed_roles: ["admin"], is_active: false })],
    });

    await act(async () => {
      await result.current.refetchPermissions();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.canAccess("export_data")).toBe(false);
    expect(listSpy).toHaveBeenCalledTimes(2);
  });

  it("refetchPermissions recovers from fail-closed error state", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    const listSpy = vi.spyOn(apiAdmin, "listSessionFeatures");

    listSpy.mockRejectedValueOnce(new apiAdmin.AdminApiError(500, "boom"));

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
    expect(result.current.canAccess("watchlist")).toBe(false);

    listSpy.mockResolvedValueOnce({
      items: [makeFeature("watchlist", { allowed_roles: ["admin", "trader"] })],
    });

    await act(async () => {
      await result.current.refetchPermissions();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.canAccess("watchlist")).toBe(true);
  });

  it("starts in isLoading=true until permissions resolve", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    let resolveFetch: (value: { items: ReturnType<typeof makeFeature>[] }) => void;
    vi.spyOn(apiAdmin, "listSessionFeatures").mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    );

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    expect(result.current.isLoading).toBe(true);

    await act(async () => {
      resolveFetch!({ items: [makeFeature("watchlist", { allowed_roles: ["admin"] })] });
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });

  it("passes AbortSignal to listSessionFeatures (M-2)", async () => {
    mockUseAuth.mockReturnValue(adminAuth());
    const listSpy = vi.spyOn(apiAdmin, "listSessionFeatures").mockResolvedValue({
      items: [makeFeature("watchlist", { allowed_roles: ["admin"] })],
    });

    const { result } = renderHook(() => useFeaturePermissions(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(listSpy).toHaveBeenCalled();
    const arg = listSpy.mock.calls[0]?.[0];
    expect(arg?.signal).toBeInstanceOf(AbortSignal);
  });
});

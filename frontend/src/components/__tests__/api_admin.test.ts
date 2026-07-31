import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  AdminApiError,
  adminErrorMessage,
  listAdminUsers,
  updateFeaturePermission,
  updateUserRole,
  listAdminFeatures,
  listSessionFeatures,
} from "../../api_admin";

describe("api_admin", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listAdminUsers sends page size and search", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], total: 0, page: 1, size: 20 }),
    });
    await listAdminUsers({ page: 2, size: 20, search: "alice" });
    expect(fetchMock).toHaveBeenCalled();
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/admin/users");
    expect(url).toContain("page=2");
    expect(url).toContain("size=20");
    expect(url).toContain("search=alice");
    expect(fetchMock.mock.calls[0][1].credentials).toBe("include");
  });

  it("updateUserRole throws AdminApiError with detail on 400", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: async () => ({ detail: "Cannot demote the last active admin" }),
    });
    await expect(updateUserRole("u1", "trader")).rejects.toMatchObject({
      name: "AdminApiError",
      status: 400,
      detail: "Cannot demote the last active admin",
    });
  });

  it("updateFeaturePermission sends allowed_roles only", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "1",
        feature_key: "watchlist",
        description: "W",
        allowed_roles: ["admin"],
        is_active: true,
        created_at: "",
        updated_at: "",
      }),
    });
    await updateFeaturePermission("watchlist", { allowed_roles: ["admin"] });
    const init = fetchMock.mock.calls[0][1];
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ allowed_roles: ["admin"] });
    expect(JSON.parse(init.body).is_active).toBeUndefined();
  });

  it("listAdminFeatures returns items", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [{ feature_key: "watchlist" }] }),
    });
    const data = await listAdminFeatures();
    expect(data.items[0].feature_key).toBe("watchlist");
  });

  it("listSessionFeatures calls GET /features", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [{ feature_key: "watchlist" }] }),
    });
    const data = await listSessionFeatures();
    expect(fetchMock).toHaveBeenCalled();
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/features");
    expect(url).not.toContain("/admin/features");
    expect(data.items[0].feature_key).toBe("watchlist");
  });

  it("adminErrorMessage prefers AdminApiError detail", () => {
    expect(adminErrorMessage(new AdminApiError(403, "Admin privileges required"))).toBe(
      "Admin privileges required",
    );
  });

  it("adminFetch attaches AbortSignal and credentials (M-3/H-1)", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [] }),
    });
    await listAdminFeatures();
    const init = fetchMock.mock.calls[0][1];
    expect(init.credentials).toBe("include");
    expect(init.signal).toBeDefined();
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });
});

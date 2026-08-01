import { describe, expect, it } from "vitest";
import { ADMIN_NAV, RETAIL_NAV, isNavActive } from "../../layout/navConfig";

describe("navConfig admin (AC-ACC-04 / AC-REG-01)", () => {
  it("includes Admin panel path /admin", () => {
    const admin = ADMIN_NAV.find((i) => i.id === "admin-panel");
    expect(admin).toBeTruthy();
    expect(admin?.path).toBe("/admin");
  });

  it("retail nav does not include admin panel", () => {
    expect(RETAIL_NAV.some((i) => i.path.startsWith("/admin"))).toBe(false);
  });

  it("admin panel active only on exact /admin not /admin/logs", () => {
    const item = ADMIN_NAV.find((i) => i.id === "admin-panel")!;
    expect(isNavActive("/admin", item)).toBe(true);
    expect(isNavActive("/admin/logs", item)).toBe(false);
    expect(isNavActive("/admin/command", item)).toBe(false);
  });

  it("logs/command items exist for admin nav set", () => {
    expect(ADMIN_NAV.some((i) => i.path === "/admin/logs")).toBe(true);
    expect(ADMIN_NAV.some((i) => i.path === "/admin/command")).toBe(true);
  });
});

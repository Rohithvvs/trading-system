import { describe, it, expect } from "vitest";
import { ADMIN_NAV, RETAIL_NAV, isNavActive } from "./navConfig";

/**
 * 026-remove-multi-user — US3 / FR-010-01 / FR-011-01 / SC-001
 * Navigation shell must not expose profile, login, signup, or logout.
 */
describe("navConfig single-user shell", () => {
  it("RETAIL_NAV has no profile, login, signup, or logout entries (US3, SC-001)", () => {
    const ids = RETAIL_NAV.map((item) => item.id);
    const paths = RETAIL_NAV.map((item) => item.path.toLowerCase());
    const labels = RETAIL_NAV.map((item) => item.label.toLowerCase());

    expect(ids).not.toContain("profile");
    expect(ids).not.toContain("login");
    expect(ids).not.toContain("signup");
    expect(ids).not.toContain("logout");
    expect(paths.some((p) => p.includes("profile") || p.includes("login") || p.includes("signup"))).toBe(
      false,
    );
    expect(labels.some((l) => l.includes("profile") || l.includes("login") || l.includes("logout"))).toBe(
      false,
    );
  });

  it("RETAIL_NAV retains trading research destinations (FR-013-01)", () => {
    const ids = RETAIL_NAV.map((item) => item.id);
    expect(ids).toEqual(expect.arrayContaining(["markets", "scanner", "paper", "performance"]));
  });

  it("ADMIN_NAV does not include user-auth admin pages", () => {
    const paths = ADMIN_NAV.map((item) => item.path);
    expect(paths.some((p) => p.includes("/login") || p.includes("/profile") || p.includes("/auth"))).toBe(
      false,
    );
  });

  it("isNavActive matches prefix paths for paper desk", () => {
    const paper = RETAIL_NAV.find((i) => i.id === "paper")!;
    expect(isNavActive("/paper", paper)).toBe(true);
    expect(isNavActive("/paper/positions", paper)).toBe(true);
    expect(isNavActive("/scanner", paper)).toBe(false);
  });

  it("edge: root path matching only exact when match is /", () => {
    const fake = { id: "root", label: "Root", path: "/", match: "/", icon: null, testId: "nav-root" };
    expect(isNavActive("/", fake)).toBe(true);
    expect(isNavActive("/scanner", fake)).toBe(false);
  });
});

import { describe, expect, it } from "vitest";
import { DEFAULT_FEATURE_CATALOG } from "../featureCatalogDefaults";
import type { FeatureKey } from "../../types/featurePermissions";

const REQUIRED_KEYS: FeatureKey[] = [
  "admin_panel",
  "user_management",
  "system_logs",
  "central_command",
  "export_data",
  "watchlist",
  "portfolio_analytics",
  "advanced_scanner",
];

describe("DEFAULT_FEATURE_CATALOG (trader fallback matrix)", () => {
  it("includes all known FeatureKey entries", () => {
    for (const key of REQUIRED_KEYS) {
      expect(DEFAULT_FEATURE_CATALOG[key]).toBeDefined();
      expect(DEFAULT_FEATURE_CATALOG[key].feature_key).toBe(key);
    }
  });

  it("marks all default features as active", () => {
    for (const key of REQUIRED_KEYS) {
      expect(DEFAULT_FEATURE_CATALOG[key].is_active).toBe(true);
    }
  });

  it("grants trader + admin on retail surfaces (watchlist, scanner, portfolio)", () => {
    expect(DEFAULT_FEATURE_CATALOG.watchlist.allowed_roles).toEqual(
      expect.arrayContaining(["trader", "admin"]),
    );
    expect(DEFAULT_FEATURE_CATALOG.advanced_scanner.allowed_roles).toEqual(
      expect.arrayContaining(["trader", "admin"]),
    );
    expect(DEFAULT_FEATURE_CATALOG.portfolio_analytics.allowed_roles).toEqual(
      expect.arrayContaining(["trader", "admin"]),
    );
  });

  it("restricts admin-only surfaces to admin role", () => {
    const adminOnly: FeatureKey[] = [
      "export_data",
      "system_logs",
      "central_command",
      "admin_panel",
      "user_management",
    ];

    for (const key of adminOnly) {
      expect(DEFAULT_FEATURE_CATALOG[key].allowed_roles).toEqual(["admin"]);
      expect(DEFAULT_FEATURE_CATALOG[key].allowed_roles).not.toContain("trader");
    }
  });

  it("provides stable shape for FeaturePermission records", () => {
    const sample = DEFAULT_FEATURE_CATALOG.watchlist;
    expect(sample).toMatchObject({
      id: expect.any(String),
      feature_key: "watchlist",
      description: expect.any(String),
      allowed_roles: expect.any(Array),
      is_active: true,
      created_at: expect.any(String),
      updated_at: expect.any(String),
    });
  });
});

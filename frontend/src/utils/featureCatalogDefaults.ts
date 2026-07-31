import type { FeaturePermission, FeatureKey } from "../types/featurePermissions";

/**
 * Client-side default feature permissions matrix.
 * Used for non-admin (`trader`) users when GET /admin/features returns 403 Forbidden.
 * Ensures traders receive default access without backend API modifications.
 */
export const DEFAULT_FEATURE_CATALOG: Record<string, FeaturePermission> = {
  watchlist: {
    id: "default-watchlist",
    feature_key: "watchlist",
    description: "Watchlist management and views",
    allowed_roles: ["trader", "admin"],
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  advanced_scanner: {
    id: "default-advanced_scanner",
    feature_key: "advanced_scanner",
    description: "Advanced scanner tools and views",
    allowed_roles: ["trader", "admin"],
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  portfolio_analytics: {
    id: "default-portfolio_analytics",
    feature_key: "portfolio_analytics",
    description: "Portfolio analytics and reports",
    allowed_roles: ["trader", "admin"],
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  export_data: {
    id: "default-export_data",
    feature_key: "export_data",
    description: "Export data from the platform",
    allowed_roles: ["admin"],
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  system_logs: {
    id: "default-system_logs",
    feature_key: "system_logs",
    description: "View system and operational logs",
    allowed_roles: ["admin"],
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  central_command: {
    id: "default-central_command",
    feature_key: "central_command",
    description: "Operational central command console",
    allowed_roles: ["admin"],
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  admin_panel: {
    id: "default-admin_panel",
    feature_key: "admin_panel",
    description: "Access to the administrative console",
    allowed_roles: ["admin"],
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  user_management: {
    id: "default-user_management",
    feature_key: "user_management",
    description: "List users and change roles",
    allowed_roles: ["admin"],
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
};

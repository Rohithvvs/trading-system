import type { ReactNode } from "react";

export type FeatureKey =
  | "admin_panel"
  | "user_management"
  | "system_logs"
  | "central_command"
  | "export_data"
  | "watchlist"
  | "portfolio_analytics"
  | "advanced_scanner"
  | "recommendation_lab";

export interface FeaturePermission {
  id: string;
  feature_key: FeatureKey | string;
  description: string;
  allowed_roles: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FeaturePermissionsContextType {
  permissions: Record<string, FeaturePermission>;
  isLoading: boolean;
  error: Error | null;
  canAccess: (featureKey: FeatureKey | string) => boolean;
  refetchPermissions: () => Promise<void>;
}

export interface FeatureGuardProps {
  feature: FeatureKey | string;
  children: ReactNode;
  fallback?: ReactNode;
  loadingFallback?: ReactNode;
}

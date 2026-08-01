# Data Model & Frontend Types: Sprint 5 – Frontend Feature Guards

**Feature Directory**: `specs/026-feature-guards`  
**Date**: 2026-07-31  

---

## 1. Type Definitions

### FeatureKey Union Type
```ts
export type FeatureKey =
  | "admin_panel"
  | "user_management"
  | "system_logs"
  | "central_command"
  | "export_data"
  | "watchlist"
  | "portfolio_analytics"
  | "advanced_scanner";
```

### FeaturePermission Entity (Matching Sprint 3 Backend DTO)
```ts
export interface FeaturePermission {
  id: string;
  feature_key: FeatureKey | string;
  description: string;
  allowed_roles: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
```

### FeaturePermissionsContext Type
```ts
export interface FeaturePermissionsContextType {
  permissions: Record<string, FeaturePermission>;
  isLoading: boolean;
  error: Error | null;
  canAccess: (featureKey: string) => boolean;
  refetchPermissions: () => Promise<void>;
}
```

### FeatureGuard Component Props
```ts
export interface FeatureGuardProps {
  feature: FeatureKey | string;
  children: React.ReactNode;
  fallback?: React.ReactNode;
  loadingFallback?: React.ReactNode;
}
```

### Extended NavItem (Navigation Config)
```ts
export interface NavItem {
  id: string;
  label: string;
  path: string;
  match?: string;
  icon: React.ReactNode;
  testId: string;
  featureKey?: FeatureKey | string; // Extended in Sprint 5
}
```

---

## 2. Default Trader Permission Catalog Matrix

When non-admin users (`user.role === "trader"`) fetch permissions, `FeaturePermissionsContext` supplies the standard default matrix:

| Feature Key | Description | Default `allowed_roles` | Default `is_active` |
| :--- | :--- | :--- | :--- |
| `watchlist` | Watchlist management and views | `["trader", "admin"]` | `true` |
| `advanced_scanner` | Advanced scanner tools and views | `["trader", "admin"]` | `true` |
| `portfolio_analytics` | Portfolio analytics and reports | `["trader", "admin"]` | `true` |
| `export_data` | Export data from the platform | `["admin"]` | `true` |
| `system_logs` | View system and operational logs | `["admin"]` | `true` |
| `central_command` | Operational central command console | `["admin"]` | `true` |
| `admin_panel` | Access to the administrative console | `["admin"]` | `true` |
| `user_management` | List users and change roles | `["admin"]` | `true` |

# Component & Hook Contracts: Sprint 5 – Feature Guards

**Feature Directory**: `specs/026-feature-guards`  
**Date**: 2026-07-31  
**Related**: [RELEASE_NOTES.md](../RELEASE_NOTES.md)

---

## 0. Session catalog API (backend complement)

```http
GET /features
Authorization: Bearer <access_token>   # or session cookie
```

**Response** (200): `{ "items": FeaturePermission[] }`  
**Auth**: any active authenticated user  
**401**: unauthenticated  
**Mutations**: remain on `PATCH /admin/features/{feature_key}` (admin only)

SPA loads this catalog via `listSessionFeatures()` → `FeaturePermissionsProvider`.

---

## 1. `useFeaturePermissions` Hook Contract

```ts
function useFeaturePermissions(): {
  permissions: Record<string, FeaturePermission>;
  isLoading: boolean;
  error: Error | null;
  canAccess: (featureKey: string) => boolean;
  refetchPermissions: () => Promise<void>;
}
```

### Usage Example
```tsx
import { useFeaturePermissions } from "../hooks/useFeaturePermissions";

function ExportDataButton() {
  const { canAccess } = useFeaturePermissions();

  if (!canAccess("export_data")) {
    return null;
  }

  return <button onClick={handleExport}>Export Report</button>;
}
```

---

## 2. `<FeatureGuard>` Component Contract

```tsx
function FeatureGuard(props: {
  feature: string;
  children: React.ReactNode;
  fallback?: React.ReactNode;
  loadingFallback?: React.ReactNode;
}): React.ReactElement | null;
```

### Usage Examples

#### Inline Component Protection
```tsx
<FeatureGuard feature="watchlist" fallback={<p>Watchlist is currently disabled.</p>}>
  <WatchlistWidget />
</FeatureGuard>
```

#### Page Route Protection
```tsx
<Route
  path="/scanner"
  element={
    <FeatureGuard feature="advanced_scanner" fallback={<AccessDenied />}>
      <CandidateTable />
    </FeatureGuard>
  }
/>
```

---

## 3. `<AccessDenied>` Component Contract

```tsx
function AccessDenied(props?: {
  title?: string;
  message?: string;
  returnPath?: string;
}): React.ReactElement;
```

### Render Output
Renders a centered card with an access denied icon, title ("Access Denied"), descriptive message ("You do not have permission to view this feature."), and a button to return to `/markets`.

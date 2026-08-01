import React from "react";
import { useFeaturePermissions } from "../hooks/useFeaturePermissions";
import type { FeatureGuardProps } from "../types/featurePermissions";

/** Default loading shell while permissions resolve (audit M-3). */
function DefaultLoadingFallback() {
  return (
    <div
      data-testid="feature-guard-loading"
      className="page-container flex flex-col items-center justify-center min-h-[40vh] text-center px-4"
      style={{ padding: "24px 16px" }}
      aria-busy="true"
      aria-live="polite"
    >
      <div
        className="app-skel"
        style={{ width: 220, height: 12, borderRadius: 8, marginBottom: 12 }}
      />
      <p className="text-gray-400 text-sm">Checking access…</p>
    </div>
  );
}

/**
 * Declarative component guard for protecting UI components and page routes based on feature permissions.
 *
 * Usage:
 * `<FeatureGuard feature="watchlist"><WatchlistWidget /></FeatureGuard>`
 * `<FeatureGuard feature="advanced_scanner" fallback={<AccessDenied />}><ScannerPage /></FeatureGuard>`
 */
export const FeatureGuard: React.FC<FeatureGuardProps> = ({
  feature,
  children,
  fallback = null,
  loadingFallback,
}) => {
  const { canAccess, isLoading } = useFeaturePermissions();

  if (isLoading) {
    // undefined → default skeleton; explicit null → render nothing (inline controls)
    if (loadingFallback === null) return null;
    if (loadingFallback !== undefined) return <>{loadingFallback}</>;
    return <DefaultLoadingFallback />;
  }

  if (!canAccess(feature)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
};

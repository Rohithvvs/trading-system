import { useContext } from "react";
import { FeaturePermissionsContext } from "../contexts/FeaturePermissionsContext";
import type { FeaturePermissionsContextType } from "../types/featurePermissions";

/**
 * Fail-closed fallback when used outside FeaturePermissionsProvider (audit H-3).
 * Production trees must wrap with FeaturePermissionsProvider in App.
 */
const DENY_ALL_FALLBACK: FeaturePermissionsContextType = {
  permissions: {},
  isLoading: false,
  error: null,
  canAccess: () => false,
  refetchPermissions: async () => {},
};

/**
 * Hook to access feature permissions context and evaluate access control.
 * Outside provider: deny-all (fail-closed). Prefer mounting under FeaturePermissionsProvider.
 */
export function useFeaturePermissions(): FeaturePermissionsContextType {
  const context = useContext(FeaturePermissionsContext);
  if (!context) {
    return DENY_ALL_FALLBACK;
  }
  return context;
}

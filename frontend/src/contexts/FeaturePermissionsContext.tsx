import React, { createContext, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AdminApiError, listSessionFeatures } from "../api_admin";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../design-system";
import type {
  FeaturePermission,
  FeaturePermissionsContextType,
} from "../types/featurePermissions";
import { DEFAULT_FEATURE_CATALOG } from "../utils/featureCatalogDefaults";

export const FeaturePermissionsContext = createContext<FeaturePermissionsContextType | undefined>(
  undefined,
);

/** Normalize and validate API items; skip corrupt entries (audit M-1 hardening). */
function itemsToMap(items: FeaturePermission[]): Record<string, FeaturePermission> {
  const permMap: Record<string, FeaturePermission> = {};
  for (const item of items) {
    if (!item || typeof item !== "object") continue;
    const key = typeof item.feature_key === "string" ? item.feature_key.trim() : "";
    if (!key) continue;
    const roles = Array.isArray(item.allowed_roles)
      ? item.allowed_roles
          .map((r) => String(r).trim().toLowerCase())
          .filter(Boolean)
      : [];
    permMap[key] = {
      ...item,
      feature_key: key,
      allowed_roles: roles,
      is_active: Boolean(item.is_active),
    };
  }
  return permMap;
}

function logPermissionEvent(
  level: "info" | "warn" | "error",
  event: string,
  detail?: Record<string, unknown>,
): void {
  const payload = { event, ...detail, ts: new Date().toISOString() };
  // Structured client observability (audit L-2) — no PII / tokens
  if (level === "error") {
    console.error("[feature-permissions]", payload);
  } else if (level === "warn") {
    console.warn("[feature-permissions]", payload);
  } else if (import.meta.env?.DEV) {
    console.info("[feature-permissions]", payload);
  }
}

export const FeaturePermissionsProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { user, isAuthenticated } = useAuth();
  const toast = useToast();
  const [permissions, setPermissions] = useState<Record<string, FeaturePermission>>({});
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const fetchGenRef = useRef(0);
  const toastOnceRef = useRef(false);
  // Stable refs — avoid re-fetch loops when toast API identity changes
  const toastRef = useRef(toast);
  toastRef.current = toast;
  const userRef = useRef(user);
  userRef.current = user;
  const isAuthenticatedRef = useRef(isAuthenticated);
  isAuthenticatedRef.current = isAuthenticated;

  const userId = user?.id ?? null;
  const userRole = user?.role ?? null;

  const notifyFailClosed = useCallback((fetchError: Error, reason: string) => {
    setError(fetchError);
    setPermissions({});
    logPermissionEvent("warn", "permissions_fail_closed", {
      reason,
      message: fetchError.message,
    });
    if (!toastOnceRef.current) {
      toastOnceRef.current = true;
      toastRef.current.warning(
        "Feature permissions unavailable",
        "Some features are temporarily restricted. Retry from your profile or refresh later.",
      );
    }
  }, []);

  const fetchPermissions = useCallback(async () => {
    // Abort in-flight request (concurrency / no retry storms)
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const gen = ++fetchGenRef.current;

    setIsLoading(true);
    setError(null);

    const auth = isAuthenticatedRef.current;
    const currentUser = userRef.current;

    if (!auth || !currentUser) {
      setPermissions({});
      setIsLoading(false);
      return;
    }

    try {
      const response = await listSessionFeatures({ signal: controller.signal });

      if (gen !== fetchGenRef.current) {
        return;
      }

      if (!response || !Array.isArray(response.items)) {
        notifyFailClosed(new Error("Invalid feature permissions payload"), "invalid_payload");
        return;
      }

      const permMap = itemsToMap(response.items);
      // Empty catalog after filter is still a resolved state (deny unknown keys)
      setPermissions(permMap);
      setError(null);
      toastOnceRef.current = false;
      logPermissionEvent("info", "permissions_loaded", { count: Object.keys(permMap).length });
    } catch (err) {
      if (gen !== fetchGenRef.current) {
        return;
      }
      // AbortError from intentional cancel — leave state for the newer request
      if (
        (err instanceof DOMException && err.name === "AbortError") ||
        (err instanceof Error && err.name === "AbortError") ||
        controller.signal.aborted
      ) {
        return;
      }

      // Only HTTP 403 uses client default catalog (legacy safety net for traders).
      // Unresolvable errors fail closed for ALL roles (audit H-1 / AC-FEAT-06).
      const is403 = err instanceof AdminApiError && err.status === 403;

      if (is403 && currentUser.role === "trader") {
        // Normalize catalog copy for consistent role matching
        setPermissions(itemsToMap(Object.values(DEFAULT_FEATURE_CATALOG)));
        setError(null);
        logPermissionEvent("info", "permissions_trader_403_catalog_fallback", {});
      } else {
        const fetchError =
          err instanceof Error ? err : new Error("Failed to load feature permissions");
        notifyFailClosed(fetchError, is403 ? "forbidden" : "fetch_error");
      }
    } finally {
      if (gen === fetchGenRef.current) {
        setIsLoading(false);
      }
    }
  }, [notifyFailClosed]);

  // Re-fetch only when session identity / role changes
  useEffect(() => {
    void fetchPermissions();
    return () => {
      abortRef.current?.abort();
    };
  }, [fetchPermissions, userId, userRole, isAuthenticated]);

  const canAccess = useCallback(
    (featureKey: string): boolean => {
      if (!featureKey || typeof featureKey !== "string") return false;
      if (!isAuthenticated || !user) return false;
      // Fail closed while initial resolution is in progress with no cached map
      if (isLoading && Object.keys(permissions).length === 0) return false;

      const key = featureKey.trim();
      if (!key) return false;

      const perm = permissions[key];
      if (!perm) return false;
      if (!perm.is_active) return false;

      const role = String(user.role || "").trim().toLowerCase();
      if (!role) return false;
      return Array.isArray(perm.allowed_roles) && perm.allowed_roles.includes(role);
    },
    [permissions, isAuthenticated, user, isLoading],
  );

  const contextValue = useMemo<FeaturePermissionsContextType>(
    () => ({
      permissions,
      isLoading,
      error,
      canAccess,
      refetchPermissions: fetchPermissions,
    }),
    [permissions, isLoading, error, canAccess, fetchPermissions],
  );

  return (
    <FeaturePermissionsContext.Provider value={contextValue}>
      {children}
    </FeaturePermissionsContext.Provider>
  );
};

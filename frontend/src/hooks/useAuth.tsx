import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { authMe, authLogout } from '../api';
import { cachedFetch, CACHE_KEYS, getCached, setCached, setCacheUserScope } from '../utils/appCache';
import { clearAllAppCaches, prefetchAppData } from '../utils/prefetchAppData';
import { authStorage } from '../utils/storage';
import type { UserRole } from '../types/auth';
import { DEFAULT_ROLE } from '../types/auth';

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
}

interface AuthContextType {
  user: AuthUser | null;
  /** Normalized role convenience accessor (defaults to trader when unauthenticated). */
  role: UserRole;
  isAuthenticated: boolean;
  /** True only when we have no cached user and network validation is in flight. */
  isLoading: boolean;
  /** True while background revalidation is running (UI should already be visible). */
  isRevalidating: boolean;
  login: (user: AuthUser) => void;
  logout: () => void;
  /** Update header/sidebar user after profile save (no full reload). */
  updateUser: (partial: Partial<AuthUser>) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const USER_STORAGE_KEY = 'user';

function normalizeRole(role: unknown): UserRole {
  return role === 'admin' ? 'admin' : DEFAULT_ROLE;
}

function normalizeAuthUser(raw: Partial<AuthUser> | null | undefined): AuthUser | null {
  if (!raw?.id || !raw?.email) return null;
  return {
    id: String(raw.id),
    email: raw.email,
    full_name: raw.full_name || '',
    role: normalizeRole(raw.role),
  };
}

function persistUser(user: AuthUser | null): void {
  if (!user) {
    try {
      localStorage.removeItem(USER_STORAGE_KEY);
      sessionStorage.removeItem(USER_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    authStorage.clearAuth();
    return;
  }
  // Single source: authStorage (sessionStorage). Do not keep durable localStorage user blob.
  try {
    localStorage.removeItem(USER_STORAGE_KEY);
  } catch {
    /* ignore */
  }
  authStorage.setUserProfile({
    id: user.id,
    email: user.email,
    full_name: user.full_name,
    role: user.role,
  });
}

function readStoredUser(): AuthUser | null {
  // Prefer shared app cache (TTL-aware, in-memory)
  const fromCache = normalizeAuthUser(getCached<AuthUser>(CACHE_KEYS.authMe));
  if (fromCache) return fromCache;

  // Prefer dedicated role-aware auth storage (sessionStorage)
  const fromAuthStorage = normalizeAuthUser(authStorage.getUserProfile());
  if (fromAuthStorage) return fromAuthStorage;

  // Legacy one-time migrate from localStorage 'user' then purge
  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthUser>;
    if (parsed && !parsed.role) {
      parsed.role = authStorage.getUserRole();
    }
    const normalized = normalizeAuthUser(parsed);
    if (normalized) {
      authStorage.setUserProfile(normalized);
      localStorage.removeItem(USER_STORAGE_KEY);
    }
    return normalized;
  } catch {
    /* ignore */
  }
  return null;
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Instant paint: hydrate from localStorage / cache — never block shell on network
  const [user, setUser] = useState<AuthUser | null>(() => {
    const u = readStoredUser();
    if (u?.id) setCacheUserScope(u.id);
    return u;
  });
  const [isLoading, setIsLoading] = useState(() => !readStoredUser());
  const [isRevalidating, setIsRevalidating] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const validateSession = async () => {
      const hadCachedUser = !!readStoredUser();
      if (hadCachedUser) {
        setIsRevalidating(true);
      } else {
        setIsLoading(true);
      }

      try {
        const raw = await cachedFetch(CACHE_KEYS.authMe, () => authMe(), {
          force: !hadCachedUser,
          softTimeoutMs: 4000,
          swr: hadCachedUser,
        });
        if (cancelled) return;
        const userData = normalizeAuthUser(raw);
        if (!userData) throw new Error('Invalid auth/me payload');
        setCacheUserScope(userData.id);
        setUser(userData);
        persistUser(userData);
        setCached(CACHE_KEYS.authMe, userData);
        // Warm trading data after confirmed session
        prefetchAppData();
      } catch {
        if (cancelled) return;
        // Only clear session if we had no optimistic user, or server said unauthorized
        // Keep optimistic user briefly if network blip — clear on hard failure without cache
        if (!hadCachedUser) {
          setUser(null);
          setCacheUserScope(null);
          persistUser(null);
        } else {
          // Re-check without cache to detect true logout / 401
          try {
            const freshRaw = await authMe();
            if (cancelled) return;
            const fresh = normalizeAuthUser(freshRaw);
            if (!fresh) throw new Error('Invalid auth/me payload');
            setCacheUserScope(fresh.id);
            setUser(fresh);
            persistUser(fresh);
            setCached(CACHE_KEYS.authMe, fresh);
            prefetchAppData();
          } catch {
            if (cancelled) return;
            setUser(null);
            setCacheUserScope(null);
            persistUser(null);
            clearAllAppCaches();
          }
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          setIsRevalidating(false);
        }
      }
    };

    void validateSession();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback((userData: AuthUser) => {
    const normalized = normalizeAuthUser(userData);
    if (!normalized) return;
    setCacheUserScope(normalized.id);
    setUser(normalized);
    persistUser(normalized);
    setCached(CACHE_KEYS.authMe, normalized);
    prefetchAppData();
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setCacheUserScope(null);
    persistUser(null);
    clearAllAppCaches();
    void authLogout();
  }, []);

  const updateUser = useCallback((partial: Partial<AuthUser>) => {
    setUser((prev) => {
      if (!prev) return prev;
      const next = normalizeAuthUser({ ...prev, ...partial }) || prev;
      try {
        persistUser(next);
        setCached(CACHE_KEYS.authMe, next);
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      user,
      role: user?.role ?? DEFAULT_ROLE,
      isAuthenticated: !!user,
      isLoading,
      isRevalidating,
      login,
      logout,
      updateUser,
    }),
    [user, isLoading, isRevalidating, login, logout, updateUser],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

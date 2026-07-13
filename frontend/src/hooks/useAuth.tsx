import React, { createContext, useContext, useState, useEffect, useCallback, useMemo } from 'react';
import { authMe, authLogout } from '../api';
import { cachedFetch, CACHE_KEYS, getCached, setCached, setCacheUserScope } from '../utils/appCache';
import { clearAllAppCaches, prefetchAppData } from '../utils/prefetchAppData';

interface AuthUser {
  id: string;
  email: string;
  full_name: string;
}

interface AuthContextType {
  user: AuthUser | null;
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

function readStoredUser(): AuthUser | null {
  // Prefer shared app cache (TTL-aware)
  const fromCache = getCached<AuthUser>(CACHE_KEYS.authMe);
  if (fromCache?.id) return fromCache;

  try {
    const raw = localStorage.getItem(USER_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthUser;
    if (parsed?.id && parsed?.email) return parsed;
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
        const userData = await cachedFetch(CACHE_KEYS.authMe, () => authMe(), {
          force: !hadCachedUser,
          softTimeoutMs: 4000,
          swr: hadCachedUser,
        });
        if (cancelled) return;
        setCacheUserScope(userData.id);
        setUser(userData);
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userData));
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
          localStorage.removeItem(USER_STORAGE_KEY);
        } else {
          // Re-check without cache to detect true logout / 401
          try {
            const fresh = await authMe();
            if (cancelled) return;
            setCacheUserScope(fresh.id);
            setUser(fresh);
            localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(fresh));
            setCached(CACHE_KEYS.authMe, fresh);
            prefetchAppData();
          } catch {
            if (cancelled) return;
            setUser(null);
            setCacheUserScope(null);
            localStorage.removeItem(USER_STORAGE_KEY);
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
    setCacheUserScope(userData.id);
    setUser(userData);
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userData));
    setCached(CACHE_KEYS.authMe, userData);
    prefetchAppData();
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    setCacheUserScope(null);
    localStorage.removeItem(USER_STORAGE_KEY);
    clearAllAppCaches();
    void authLogout();
  }, []);

  const updateUser = useCallback((partial: Partial<AuthUser>) => {
    setUser((prev) => {
      if (!prev) return prev;
      const next = { ...prev, ...partial };
      try {
        localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(next));
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

import { UserRole, DEFAULT_ROLE, UserProfile } from '../types/auth';

/**
 * Prefer sessionStorage for role/profile (M-5): cleared when the tab closes,
 * reducing long-lived stale privilege UI. Migrates/clears legacy localStorage keys.
 */
const STORAGE_KEYS = {
  USER_ROLE: 'auth_user_role',
  USER_PROFILE: 'auth_user_profile',
  /** @deprecated JWT must not live in browser storage. */
  LEGACY_ACCESS_TOKEN: 'auth_access_token',
  /** @deprecated legacy full user blob in localStorage */
  LEGACY_USER: 'user',
} as const;

function primaryStore(): Storage | null {
  try {
    return sessionStorage;
  } catch {
    return null;
  }
}

function legacyLocal(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

function readString(key: string): string | null {
  const session = primaryStore();
  if (session) {
    const v = session.getItem(key);
    if (v != null) return v;
  }
  // One-time migrate from localStorage → sessionStorage
  const local = legacyLocal();
  if (local) {
    const legacy = local.getItem(key);
    if (legacy != null && session) {
      try {
        session.setItem(key, legacy);
        local.removeItem(key);
      } catch {
        /* ignore */
      }
      return legacy;
    }
    return legacy;
  }
  return null;
}

function writeString(key: string, value: string): void {
  const session = primaryStore();
  if (session) {
    session.setItem(key, value);
  }
  // Purge durable localStorage copy so role does not survive tab close.
  const local = legacyLocal();
  if (local) {
    try {
      local.removeItem(key);
    } catch {
      /* ignore */
    }
  }
}

function removeKey(key: string): void {
  try {
    primaryStore()?.removeItem(key);
  } catch {
    /* ignore */
  }
  try {
    legacyLocal()?.removeItem(key);
  } catch {
    /* ignore */
  }
}

export const authStorage = {
  /**
   * Browser SPA auth relies on HttpOnly cookies. Always returns null.
   */
  getAccessToken(): string | null {
    removeKey(STORAGE_KEYS.LEGACY_ACCESS_TOKEN);
    return null;
  },

  setAccessToken(_token: string): void {
    removeKey(STORAGE_KEYS.LEGACY_ACCESS_TOKEN);
  },

  getUserRole(): UserRole {
    try {
      const role = readString(STORAGE_KEYS.USER_ROLE);
      if (role === 'admin' || role === 'trader') {
        return role;
      }
      return DEFAULT_ROLE;
    } catch {
      return DEFAULT_ROLE;
    }
  },

  setUserRole(role: UserRole): void {
    try {
      writeString(STORAGE_KEYS.USER_ROLE, role);
    } catch (e) {
      console.warn('Failed to save user role to storage', e);
    }
  },

  getUserProfile(): UserProfile | null {
    try {
      const data = readString(STORAGE_KEYS.USER_PROFILE);
      if (!data) return null;
      const parsed = JSON.parse(data);
      return {
        ...parsed,
        role: parsed.role === 'admin' ? 'admin' : 'trader',
      };
    } catch {
      return null;
    }
  },

  setUserProfile(profile: UserProfile): void {
    try {
      writeString(STORAGE_KEYS.USER_PROFILE, JSON.stringify(profile));
      this.setUserRole(profile.role);
      removeKey(STORAGE_KEYS.LEGACY_ACCESS_TOKEN);
      removeKey(STORAGE_KEYS.LEGACY_USER);
    } catch (e) {
      console.warn('Failed to save user profile to storage', e);
    }
  },

  clearAuth(): void {
    removeKey(STORAGE_KEYS.LEGACY_ACCESS_TOKEN);
    removeKey(STORAGE_KEYS.USER_ROLE);
    removeKey(STORAGE_KEYS.USER_PROFILE);
    removeKey(STORAGE_KEYS.LEGACY_USER);
  },
};

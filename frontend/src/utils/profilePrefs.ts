/**
 * Profile preferences mapping helpers.
 *
 * Primary storage is the backend (GET/PUT/PATCH /auth/profile).
 * localStorage is only used as an offline read cache after a successful server load —
 * never as the source of truth.
 */

export type ProfilePreferences = {
  phone?: string;
  country?: string;
  state?: string;
  city?: string;
  language?: string;
  currency?: string;
  timezone?: string;
  address?: string;
  postalCode?: string;
  dateOfBirth?: string;
  displayName?: string;
  username?: string;
  bio?: string;
  tradingExperience?: string;
  riskProfile?: string;
  scannerMode?: "swing" | "intraday" | "positional";
  defaultTimeframe?: string;
  defaultUniverse?: string;
  dashboardLayout?: "compact" | "comfortable";
  themePreference?: "dark" | "light" | "system";
  notifications?: {
    email: boolean;
    browser: boolean;
    scanner: boolean;
    priceAlerts: boolean;
    portfolioAlerts: boolean;
    weeklyReport: boolean;
    monthlyReport: boolean;
  };
  watchlist?: string[];
  recentlyViewed?: string[];
};

export const DEFAULT_PREFS: ProfilePreferences = {
  country: "India",
  language: "English",
  currency: "INR",
  timezone: "Asia/Kolkata",
  scannerMode: "swing",
  defaultTimeframe: "1d",
  defaultUniverse: "NIFTY500",
  dashboardLayout: "comfortable",
  themePreference: "dark",
  notifications: {
    email: true,
    browser: true,
    scanner: true,
    priceAlerts: true,
    portfolioAlerts: true,
    weeklyReport: true,
    monthlyReport: false,
  },
  watchlist: [],
  recentlyViewed: [],
};

const CACHE_PREFIX = "profile_server_cache_";

function cacheKey(userId: string) {
  return `${CACHE_PREFIX}${userId}`;
}

/** Map API profile payload → UI preferences shape */
export function profileFromApi(api: any): ProfilePreferences {
  if (!api) return { ...DEFAULT_PREFS };
  const prefs = api.preferences || {};
  const notifications = {
    ...DEFAULT_PREFS.notifications!,
    ...(prefs.notifications || {}),
  };
  return {
    ...DEFAULT_PREFS,
    displayName: api.display_name ?? prefs.displayName,
    username: api.username ?? prefs.username,
    phone: api.phone ?? undefined,
    country: api.country ?? DEFAULT_PREFS.country,
    state: api.state ?? undefined,
    city: api.city ?? undefined,
    language: api.language ?? DEFAULT_PREFS.language,
    currency: api.currency ?? DEFAULT_PREFS.currency,
    timezone: api.timezone ?? DEFAULT_PREFS.timezone,
    address: api.address ?? undefined,
    postalCode: api.postal_code ?? undefined,
    dateOfBirth: api.date_of_birth ?? undefined,
    bio: api.bio ?? undefined,
    tradingExperience: api.trading_experience ?? undefined,
    riskProfile: api.risk_profile ?? undefined,
    scannerMode: prefs.scannerMode ?? DEFAULT_PREFS.scannerMode,
    defaultTimeframe: prefs.defaultTimeframe ?? DEFAULT_PREFS.defaultTimeframe,
    defaultUniverse: prefs.defaultUniverse ?? DEFAULT_PREFS.defaultUniverse,
    dashboardLayout: prefs.dashboardLayout ?? DEFAULT_PREFS.dashboardLayout,
    themePreference: prefs.themePreference ?? DEFAULT_PREFS.themePreference,
    notifications,
    watchlist: api.watchlist ?? prefs.watchlist ?? [],
    recentlyViewed: prefs.recentlyViewed ?? [],
  };
}

/** Map UI preferences → API update body */
export function prefsToApiPayload(prefs: ProfilePreferences): Record<string, unknown> {
  return {
    display_name: prefs.displayName || null,
    username: prefs.username || null,
    phone: prefs.phone || null,
    country: prefs.country || null,
    state: prefs.state || null,
    city: prefs.city || null,
    language: prefs.language || null,
    timezone: prefs.timezone || null,
    currency: prefs.currency || null,
    address: prefs.address || null,
    postal_code: prefs.postalCode || null,
    date_of_birth: prefs.dateOfBirth || null,
    bio: prefs.bio || null,
    trading_experience: prefs.tradingExperience || null,
    risk_profile: prefs.riskProfile || null,
    preferences: {
      scannerMode: prefs.scannerMode,
      defaultTimeframe: prefs.defaultTimeframe,
      defaultUniverse: prefs.defaultUniverse,
      dashboardLayout: prefs.dashboardLayout,
      themePreference: prefs.themePreference,
      notifications: prefs.notifications,
      watchlist: prefs.watchlist || [],
      recentlyViewed: prefs.recentlyViewed || [],
    },
  };
}

/** Read optional offline cache (never the source of truth). */
export function loadProfilePrefs(userId: string | null | undefined): ProfilePreferences {
  if (!userId) return { ...DEFAULT_PREFS };
  try {
    const raw = localStorage.getItem(cacheKey(userId));
    if (!raw) return { ...DEFAULT_PREFS };
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULT_PREFS,
      ...parsed,
      notifications: { ...DEFAULT_PREFS.notifications, ...(parsed.notifications || {}) },
    };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

/** Cache a successful server response for instant next paint only. */
export function cacheProfilePrefs(userId: string, prefs: ProfilePreferences): void {
  try {
    localStorage.setItem(cacheKey(userId), JSON.stringify(prefs));
  } catch {
    /* ignore quota */
  }
}

/**
 * @deprecated Use updateUserProfile / patchUserProfile APIs.
 * Kept as cache write so older call sites don't crash during migration.
 */
export function saveProfilePrefs(userId: string, prefs: ProfilePreferences): void {
  cacheProfilePrefs(userId, prefs);
}

export function initialsFromName(name?: string | null, email?: string | null): string {
  const base = (name || email || "U").trim();
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

/** Client-side profile preferences (extends server user without new backend tables). */

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

const DEFAULT_PREFS: ProfilePreferences = {
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

function key(userId: string) {
  return `profile_prefs_${userId}`;
}

export function loadProfilePrefs(userId: string | null | undefined): ProfilePreferences {
  if (!userId) return { ...DEFAULT_PREFS };
  try {
    const raw = localStorage.getItem(key(userId));
    if (!raw) return { ...DEFAULT_PREFS };
    return { ...DEFAULT_PREFS, ...JSON.parse(raw), notifications: { ...DEFAULT_PREFS.notifications, ...(JSON.parse(raw).notifications || {}) } };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

export function saveProfilePrefs(userId: string, prefs: ProfilePreferences): void {
  localStorage.setItem(key(userId), JSON.stringify(prefs));
}

export function initialsFromName(name?: string | null, email?: string | null): string {
  const base = (name || email || "U").trim();
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

import {
  lazy,
  memo,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  authMe,
  fetchAnalytics,
  fetchPaperTradingDashboard,
  getTokenStatus,
  fetchApiHealth,
  fetchUserProfile,
  updateUserProfile,
} from "../../api";
import { useAuth } from "../../hooks/useAuth";
import { useTheme } from "../../hooks/useTheme";
import { isFyersTokenUsable } from "../../utils/tokenStatus";
import {
  initialsFromName,
  loadProfilePrefs,
  cacheProfilePrefs,
  profileFromApi,
  prefsToApiPayload,
  type ProfilePreferences,
} from "../../utils/profilePrefs";
import { useToast } from "../../design-system";
import {
  cachedFetch,
  getCached,
  PROFILE_CACHE_KEYS,
} from "../../utils/profileDataCache";

/** Heavy: recharts only when charts visible */
const LazyEquityChart = lazy(() =>
  import("./ProfileCharts").then((m) => ({ default: m.EquityAreaChart })),
);
const LazyHoldingsPie = lazy(() =>
  import("./ProfileCharts").then((m) => ({ default: m.HoldingsPieChart })),
);
/** Heavy: sessions table only on Security tab */
const LazySettingsSessions = lazy(() =>
  import("../../pages/SettingsSessions").then((m) => ({ default: m.SettingsSessions })),
);

const PIE_COLORS = ["#3b82f6", "#06b6d4", "#a855f7", "#64748b"];

type SectionId =
  | "overview"
  | "personal"
  | "security"
  | "preferences"
  | "notifications"
  | "paper"
  | "portfolio"
  | "performance"
  | "ai"
  | "watchlist"
  | "brokers"
  | "activity"
  | "privacy"
  | "support"
  | "about";

type Props = {
  onNavigate?: (view: "scanner" | "paper-trading" | "home") => void;
  /** Simplified retail profile — hide unfinished AI coach & clutter */
  retailMode?: boolean;
};

const SIDEBAR_FULL: { id: SectionId; label: string; badge?: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "personal", label: "Personal Information" },
  { id: "security", label: "Security" },
  { id: "preferences", label: "Trading Preferences" },
  { id: "notifications", label: "Notifications" },
  { id: "paper", label: "Paper Trading" },
  { id: "portfolio", label: "Portfolio" },
  { id: "performance", label: "Performance" },
  { id: "ai", label: "AI Trading Coach", badge: "New" },
  { id: "watchlist", label: "Watchlist" },
  { id: "brokers", label: "Broker Connections" },
  { id: "activity", label: "Activity History" },
  { id: "privacy", label: "Privacy Settings" },
  { id: "support", label: "Support" },
  { id: "about", label: "About" },
];

/** Retail profile IA — Overview first, then account sections */
const SIDEBAR_RETAIL: { id: SectionId; label: string; badge?: string }[] = [
  { id: "overview", label: "Profile Overview" },
  { id: "personal", label: "Personal Info" },
  { id: "brokers", label: "Broker Connections" },
  { id: "security", label: "Security" },
  { id: "preferences", label: "Preferences & Appearance" },
  { id: "notifications", label: "Notifications" },
  { id: "paper", label: "Paper Trading Summary" },
  { id: "portfolio", label: "Holdings snapshot" },
  { id: "privacy", label: "Privacy" },
  { id: "support", label: "Support" },
  { id: "about", label: "About" },
];

function money(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

function ChartSkeleton({ height = 220 }: { height?: number }) {
  return <div className="profile-skel chart-skel" style={{ height, width: "100%", borderRadius: 12 }} />;
}

function MetricSkeleton() {
  return <div className="glass-card metric-tile-card profile-skel metric-skel" style={{ minHeight: 100 }} />;
}

export function UserProfilePage({ onNavigate, retailMode = false }: Props) {
  const SIDEBAR = retailMode ? SIDEBAR_RETAIL : SIDEBAR_FULL;
  const { user, logout, updateUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const [section, setSection] = useState<SectionId>(() => {
    try {
      const q = new URLSearchParams(window.location.search).get("section") as SectionId | null;
      if (q) return q;
    } catch {
      /* ignore */
    }
    return "overview";
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Instant shell: seed from auth context + cache (no network wait)
  const [profile, setProfile] = useState<any | null>(() => getCached(PROFILE_CACHE_KEYS.me) || user);
  const [dashboard, setDashboard] = useState<any | null>(() => getCached(PROFILE_CACHE_KEYS.dashboard));
  const [analytics, setAnalytics] = useState<any | null>(() => getCached(PROFILE_CACHE_KEYS.analytics));
  const [token, setToken] = useState<any | null>(() => getCached(PROFILE_CACHE_KEYS.token));
  const [health, setHealth] = useState<any | null>(() => getCached(PROFILE_CACHE_KEYS.health));

  const [meLoading, setMeLoading] = useState(() => !getCached(PROFILE_CACHE_KEYS.me) && !user);
  const [overviewLoading, setOverviewLoading] = useState(() => !getCached(PROFILE_CACHE_KEYS.dashboard));
  const [error, setError] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<ProfilePreferences>(() => loadProfilePrefs(user?.id));
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loadedSections, setLoadedSections] = useState<Set<SectionId>>(() => new Set(["overview"]));

  const userId = user?.id || profile?.id;

  // True while the user has unsaved form edits — server reloads must not clobber them
  const formDirtyRef = useRef(false);
  const profileHydratedRef = useRef(false);
  const userIdStable = user?.id;

  /** Load auth user + DB profile once per session (or force refresh). Never loop on `user` object identity. */
  const loadMe = useCallback(async (force = false) => {
    setMeLoading(true);
    try {
      if (user && !force) {
        setProfile((prev: any) => prev || user);
      }
      const [me, serverProfile] = await Promise.all([
        cachedFetch(PROFILE_CACHE_KEYS.me, () => authMe(), { force }).catch(() => user),
        fetchUserProfile({ force }).catch(() => null),
      ]);
      if (me) setProfile(me);
      if (serverProfile) {
        const mapped = profileFromApi(serverProfile);
        // Only hydrate editable prefs from server when:
        // - first load, or forced refresh, AND user is not mid-edit
        if (force || !profileHydratedRef.current) {
          if (!formDirtyRef.current || force) {
            setPrefs(mapped);
            formDirtyRef.current = false;
          }
          profileHydratedRef.current = true;
        } else if (!formDirtyRef.current && force) {
          setPrefs(mapped);
        }
        if (me?.id || serverProfile.user_id) {
          cacheProfilePrefs(String(me?.id || serverProfile.user_id), mapped);
        }
        // Only touch auth context when the name actually changed (avoids infinite loadMe loops)
        const nextName = (serverProfile.display_name || serverProfile.full_name || "").trim();
        const currentName = (user?.full_name || "").trim();
        if (nextName && nextName !== currentName) {
          updateUser({ full_name: nextName });
        }
      }
    } catch (e: any) {
      if (!user) setError(e?.message || "Failed to load profile");
    } finally {
      setMeLoading(false);
    }
    // Depend on stable user id only — NOT the whole user object (updateUser was recreating loadMe forever)
  }, [userIdStable, user, updateUser]);

  /** Overview bundle: paper + analytics + token — parallel, non-blocking */
  const loadOverviewData = useCallback(async (force = false) => {
    // If cache is warm, hydrate sync and skip skeleton flash
    if (!force) {
      const cd = getCached<any>(PROFILE_CACHE_KEYS.dashboard);
      const ca = getCached<any>(PROFILE_CACHE_KEYS.analytics);
      const ct = getCached<any>(PROFILE_CACHE_KEYS.token);
      if (cd) setDashboard(cd);
      if (ca) setAnalytics(ca);
      if (ct) setToken(ct);
      if (cd && ca) {
        setOverviewLoading(false);
        // Still revalidate in background
        void Promise.all([
          cachedFetch(PROFILE_CACHE_KEYS.dashboard, () => fetchPaperTradingDashboard()).catch(() => null),
          cachedFetch(PROFILE_CACHE_KEYS.analytics, () => fetchAnalytics()).catch(() => null),
          cachedFetch(PROFILE_CACHE_KEYS.token, () => getTokenStatus()).catch(() => null),
        ]).then(([dash, anal, tok]) => {
          if (dash) setDashboard(dash);
          if (anal) setAnalytics(anal);
          if (tok) setToken(tok);
        });
        return;
      }
    }

    setOverviewLoading(true);
    setError(null);
    try {
      const [dash, anal, tok] = await Promise.all([
        cachedFetch(PROFILE_CACHE_KEYS.dashboard, () => fetchPaperTradingDashboard(), { force }).catch(() => null),
        cachedFetch(PROFILE_CACHE_KEYS.analytics, () => fetchAnalytics(), { force }).catch(() => null),
        cachedFetch(PROFILE_CACHE_KEYS.token, () => getTokenStatus(), { force }).catch(() => null),
      ]);
      if (dash) setDashboard(dash);
      if (anal) setAnalytics(anal);
      if (tok) setToken(tok);
    } catch (e: any) {
      setError(e?.message || "Failed to load trading summary");
    } finally {
      setOverviewLoading(false);
    }
  }, []);

  const loadAbout = useCallback(async () => {
    try {
      const hl = await cachedFetch(PROFILE_CACHE_KEYS.health, () => fetchApiHealth());
      setHealth(hl);
    } catch {
      /* non-fatal */
    }
  }, []);

  const loadBrokers = useCallback(async () => {
    try {
      const tok = await cachedFetch(PROFILE_CACHE_KEYS.token, () => getTokenStatus());
      setToken(tok);
    } catch {
      /* non-fatal */
    }
  }, []);

  const ensurePaperData = useCallback(async () => {
    if (dashboard && analytics) return;
    await loadOverviewData();
  }, [dashboard, analytics, loadOverviewData]);

  // Mount once (and when account switches) — do NOT re-run when loadMe identity changes after updateUser
  useEffect(() => {
    let cancelled = false;
    profileHydratedRef.current = false;
    formDirtyRef.current = false;
    (async () => {
      await loadMe(false);
      if (cancelled) return;
      requestAnimationFrame(() => {
        if (!cancelled) void loadOverviewData(false);
      });
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional: hydrate per user id only
  }, [userIdStable]);

  // Section-on-demand: only fetch when tab opened
  useEffect(() => {
    if (loadedSections.has(section)) return;
    setLoadedSections((prev) => new Set(prev).add(section));

    if (section === "about") void loadAbout();
    if (section === "brokers") void loadBrokers();
    if (section === "paper" || section === "portfolio" || section === "performance" || section === "ai" || section === "activity") {
      void ensurePaperData();
    }
  }, [section, loadedSections, loadAbout, loadBrokers, ensurePaperData]);

  const refresh = useCallback(async () => {
    setError(null);
    await loadMe(true);
    await loadOverviewData(true);
    if (section === "about") await loadAbout();
  }, [loadMe, loadOverviewData, loadAbout, section]);

  const account = dashboard?.account;
  const positions = dashboard?.positions || [];
  const trades = dashboard?.trades || [];

  const fullName = profile?.full_name || user?.full_name || "Trader";
  const email = profile?.email || user?.email || "";
  const displayName = prefs.displayName || fullName;
  const username = prefs.username || (email ? email.split("@")[0] : "trader");
  const provider = profile?.provider || "email";
  const picture = profile?.profile_picture as string | null | undefined;
  const memberSince = profile?.created_at
    ? new Date(profile.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : "—";
  const fyersConnected = isFyersTokenUsable(token);
  const googleConnected = String(provider).toLowerCase() === "google";

  const completion = useMemo(() => {
    const items = [
      { label: "Profile Picture", done: Boolean(picture) },
      { label: "Email Verified", done: Boolean(profile?.is_email_verified || email) },
      { label: "Mobile Verified", done: Boolean(prefs.phone && prefs.phone.length >= 10) },
      { label: "Google Connected", done: googleConnected },
      { label: "FYERS Connected", done: fyersConnected },
      { label: "2FA Enabled", done: false },
      { label: "Address Added", done: Boolean(prefs.address) },
    ];
    const done = items.filter((i) => i.done).length;
    return { items, pct: Math.round((done / items.length) * 100) };
  }, [picture, profile, email, prefs.phone, prefs.address, googleConnected, fyersConnected]);

  const equityCurve = useMemo(() => {
    const series = analytics?.cumulative_pnl || [];
    if (!series.length) {
      const start = Number(account?.starting_balance || account?.balance || 100000);
      return [
        { date: "Start", equity: start },
        { date: "Now", equity: Number(account?.equity || start) },
      ];
    }
    const start = Number(account?.starting_balance || 100000);
    return series.map((p: any) => ({
      date: p.date,
      equity: start + Number(p.pnl || 0),
      pnl: Number(p.pnl || 0),
    }));
  }, [analytics, account]);

  const holdingsPie = useMemo(() => {
    const open = positions.filter((p: any) => (p.status || "OPEN") === "OPEN" || p.qty);
    if (!open.length) {
      return [
        { name: "Cash", value: 100 },
      ];
    }
    const invested = open.reduce((s: number, p: any) => s + Number(p.invested_value || p.qty * p.avg_entry_price || 0), 0);
    const cash = Number(account?.available_cash ?? account?.balance ?? 0);
    const total = invested + cash || 1;
    // bucket by position size tiers as market-cap proxy when sector missing
    let large = 0;
    let mid = 0;
    let small = 0;
    open.forEach((p: any) => {
      const v = Number(p.invested_value || p.qty * p.avg_entry_price || 0);
      const share = v / total;
      if (share >= 0.15) large += v;
      else if (share >= 0.05) mid += v;
      else small += v;
    });
    return [
      { name: "Large positions", value: Math.round((large / total) * 1000) / 10 },
      { name: "Mid positions", value: Math.round((mid / total) * 1000) / 10 },
      { name: "Small positions", value: Math.round((small / total) * 1000) / 10 },
      { name: "Cash", value: Math.round((cash / total) * 1000) / 10 },
    ].filter((x) => x.value > 0);
  }, [positions, account]);

  const aiInsights = useMemo(() => {
    const wr = Number(analytics?.win_rate_pct ?? 0);
    const pf = Number(analytics?.profit_factor ?? 0);
    const dd = Number(analytics?.max_drawdown_pct ?? 0);
    const strengths: string[] = [];
    const improve: string[] = [];
    if (wr >= 55) strengths.push("Solid win rate above 55%");
    else improve.push("Improve entry filters to raise win rate");
    if (pf >= 1.5) strengths.push("Healthy profit factor");
    else if (pf > 0) improve.push("Let winners run to lift profit factor");
    if (dd > 0 && dd < 10) strengths.push("Drawdown is under control");
    else if (dd >= 10) improve.push("Reduce position size to limit drawdown");
    if (!strengths.length) strengths.push("Building trade history for coaching");
    if (!improve.length) improve.push("Keep journaling each swing exit");
    const summary =
      wr > 0
        ? `Your trading discipline is ${wr >= 60 ? "improving" : "developing"}. Win rate ${wr.toFixed(1)}%. Focus on risk and consistency.`
        : "Complete a few paper trades to unlock personalized coaching.";
    return { summary, strengths, improve, score: Math.min(95, Math.round(40 + wr * 0.4 + Math.min(pf, 3) * 8)) };
  }, [analytics]);

  const activity = useMemo(() => {
    const rows: { when: string; activity: string; details: string; status: string }[] = [];
    if (profile?.updated_at) {
      rows.push({
        when: new Date(profile.updated_at).toLocaleString(),
        activity: "Profile Session",
        details: `Authenticated as ${email}`,
        status: "Success",
      });
    }
    (trades || []).slice(0, 5).forEach((t: any) => {
      rows.push({
        when: t.closed_at ? new Date(t.closed_at).toLocaleString() : "—",
        activity: "Paper Trade Close",
        details: `${t.symbol} · PnL ${money(t.pnl)}`,
        status: Number(t.pnl) >= 0 ? "Success" : "Loss",
      });
    });
    if (fyersConnected) {
      rows.push({
        when: new Date().toLocaleString(),
        activity: "FYERS Status",
        details: "Broker token active",
        status: "Success",
      });
    }
    if (!rows.length) {
      rows.push({
        when: new Date().toLocaleString(),
        activity: "Welcome",
        details: "Profile opened — start scanning or paper trading",
        status: "Info",
      });
    }
    return rows.slice(0, 8);
  }, [profile, trades, email, fyersConnected]);

  function markPrefsDraft(next: ProfilePreferences) {
    formDirtyRef.current = true;
    setPrefs(next);
  }

  async function persistPrefs(next: ProfilePreferences): Promise<boolean> {
    if (!userId) {
      toast.warning("Sign in required", "Profile is saved to your account after login.");
      return false;
    }
    setSaving(true);
    try {
      const updated = await updateUserProfile(prefsToApiPayload(next));
      const mapped = profileFromApi(updated);
      setPrefs(mapped);
      formDirtyRef.current = false;
      cacheProfilePrefs(String(userId), mapped);
      const nextName = (mapped.displayName || "").trim();
      if (nextName && nextName !== (user?.full_name || "").trim()) {
        updateUser({ full_name: nextName });
      }
      setSaveMsg("Profile saved to your account");
      toast.success("Profile saved", "Synced across devices");
      setTimeout(() => setSaveMsg(null), 2500);
      return true;
    } catch (e: any) {
      // Keep form draft — do not clear fields on API failure
      formDirtyRef.current = true;
      toast.error("Could not save profile", e?.message || "Please try again");
      return false;
    } finally {
      setSaving(false);
    }
  }

  function selectSection(id: SectionId) {
    setSection(id);
    setSidebarOpen(false);
  }

  const portfolioValue = Number(account?.equity ?? account?.balance ?? 0);
  const availableCash = Number(account?.available_cash ?? account?.balance ?? 0);
  const invested = Number(account?.total_invested ?? Math.max(0, portfolioValue - availableCash));
  const realized = Number(account?.realized_pnl ?? 0);
  const unrealized = Number(account?.unrealized_pnl ?? 0);
  const totalPnl = realized + unrealized;
  const openCount = positions.length;
  const closedCount = Number(analytics?.total_trades ?? trades.length ?? 0);
  const winRate = analytics?.win_rate_pct;
  const profitFactor = analytics?.profit_factor;
  const maxDd = analytics?.max_drawdown_pct;
  const maxDdAmt = analytics?.max_drawdown;

  // Always render shell immediately — skeletons only inside cards
  return (
    <div className="profile-page" data-testid="user-profile-page">
      {sidebarOpen ? <button type="button" className="profile-backdrop" aria-label="Close menu" onClick={() => setSidebarOpen(false)} /> : null}

      {/* Sidebar */}
      <aside className={`profile-sidebar ${sidebarOpen ? "is-open" : ""}`}>
        <div className="profile-sidebar-brand">
          <div className="profile-brand-mark">TX</div>
          <div>
            <strong>TradeX</strong>
            <span>Account Center</span>
          </div>
        </div>

        <div className="profile-sidebar-user">
          <div className="profile-avatar sm">
            {picture ? <img src={picture} alt="" /> : <span>{initialsFromName(fullName, email)}</span>}
          </div>
          <div>
            <strong>{displayName}</strong>
            <span className="muted">{email}</span>
            <span className="profile-plan-pill">Free Plan</span>
          </div>
        </div>

        <nav className="profile-nav" aria-label="Profile sections">
          {SIDEBAR.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`profile-nav-item ${section === item.id ? "is-active" : ""}`}
              onClick={() => selectSection(item.id)}
            >
              <span className="profile-nav-icon" aria-hidden>
                {navIcon(item.id)}
              </span>
              <span>{item.label}</span>
              {item.badge ? <span className="profile-badge-new">{item.badge}</span> : null}
            </button>
          ))}
        </nav>

        <div className="profile-sidebar-footer">
          <div className="profile-theme-switch" role="group" aria-label="Theme">
            <button type="button" className={theme === "dark" ? "is-active" : ""} onClick={() => setTheme("dark")}>
              Dark
            </button>
            <button type="button" className={theme === "light" ? "is-active" : ""} onClick={() => setTheme("light")}>
              Light
            </button>
            <button
              type="button"
              className={prefs.themePreference === "system" ? "is-active" : ""}
              onClick={() => {
                const prefersLight = window.matchMedia("(prefers-color-scheme: light)").matches;
                setTheme(prefersLight ? "light" : "dark");
                persistPrefs({ ...prefs, themePreference: "system" });
              }}
            >
              System
            </button>
          </div>
          <button type="button" className="button ghost-button profile-signout" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <div className="profile-main">
        <header className="profile-topbar">
          <button type="button" className="profile-menu-btn" onClick={() => setSidebarOpen((v) => !v)} aria-label="Toggle sidebar">
            ☰
          </button>
          <div>
            <h1>User Profile</h1>
            <p className="muted">Manage your account, preferences and view your trading performance</p>
          </div>
          <div className="profile-topbar-actions">
            <button type="button" className="button ghost-button" onClick={() => selectSection("personal")}>
              View Profile
            </button>
            <div className="profile-top-user">
              <div className="profile-avatar xs">
                {picture ? <img src={picture} alt="" /> : <span>{initialsFromName(fullName, email)}</span>}
              </div>
              <span>{displayName}</span>
              <span className="profile-plan-pill">Free</span>
            </div>
          </div>
        </header>

        {error ? (
          <div className="panel error-state profile-error">
            <p>{error}</p>
            <button type="button" className="button primary-button" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        ) : null}
        {saveMsg ? <div className="profile-toast">{saveMsg}</div> : null}

        {section === "overview" ? (
          <OverviewSection
            fullName={displayName}
            email={email}
            username={username}
            picture={picture}
            phone={prefs.phone}
            country={prefs.country}
            memberSince={memberSince}
            googleConnected={googleConnected}
            fyersConnected={fyersConnected}
            userId={String(userId || "—")}
            completion={completion}
            portfolioValue={portfolioValue}
            availableCash={availableCash}
            invested={invested}
            totalPnl={totalPnl}
            winRate={winRate}
            profitFactor={profitFactor}
            maxDd={maxDd}
            maxDdAmt={maxDdAmt}
            closedCount={closedCount}
            expectancy={analytics?.average_profit}
            bestTrade={analytics?.best_trade_amount}
            equityCurve={equityCurve}
            holdingsPie={holdingsPie}
            holdingsCount={openCount}
            aiInsights={aiInsights}
            activity={activity}
            metricsLoading={overviewLoading}
            meLoading={meLoading}
            onEdit={() => selectSection("personal")}
            onPassword={() => selectSection("security")}
            onPaper={() => onNavigate?.("paper-trading") || selectSection("paper")}
            onScanner={() => onNavigate?.("scanner")}
            onAi={() => selectSection("ai")}
            onPortfolio={() => selectSection("portfolio")}
            onSettings={() => selectSection("preferences")}
          />
        ) : null}

        {section === "personal" ? (
          <PersonalSection
            key={`personal-${userIdStable || "anon"}`}
            savedPrefs={prefs}
            fullName={fullName}
            email={email}
            saving={saving}
            onDirtyChange={(dirty) => {
              formDirtyRef.current = dirty;
            }}
            onSaved={async (next) => {
              await persistPrefs(next);
              return true;
            }}
          />
        ) : null}

        {section === "security" ? (
          <SecuritySection email={email} googleConnected={googleConnected} />
        ) : null}

        {section === "preferences" ? (
          <PreferencesSection
            prefs={prefs}
            theme={theme}
            onTheme={setTheme}
            onChange={markPrefsDraft}
            onSave={() => void persistPrefs(prefs)}
          />
        ) : null}

        {section === "notifications" ? (
          <NotificationsSection
            prefs={prefs}
            onChange={(n) => markPrefsDraft({ ...prefs, notifications: n })}
            onSave={() => void persistPrefs(prefs)}
          />
        ) : null}

        {section === "paper" || section === "portfolio" || section === "performance" ? (
          <PaperPerfSection
            mode={section}
            account={account}
            analytics={analytics}
            positions={positions}
            equityCurve={equityCurve}
            holdingsPie={holdingsPie}
            onNavigatePaper={() => onNavigate?.("paper-trading")}
          />
        ) : null}

        {section === "ai" ? <AiSection insights={aiInsights} analytics={analytics} /> : null}

        {section === "watchlist" ? (
          <WatchlistSection
            prefs={prefs}
            onSave={(list) => persistPrefs({ ...prefs, watchlist: list })}
          />
        ) : null}

        {section === "brokers" ? <BrokersSection fyersConnected={fyersConnected} token={token} /> : null}

        {section === "activity" ? <ActivitySection activity={activity} /> : null}

        {section === "privacy" ? <PrivacySection /> : null}

        {section === "support" ? <SupportSection /> : null}

        {section === "about" ? <AboutSection health={health} /> : null}
      </div>
    </div>
  );
}

function navIcon(id: SectionId): string {
  const map: Record<SectionId, string> = {
    overview: "▣",
    personal: "👤",
    security: "🛡",
    preferences: "⚙",
    notifications: "🔔",
    paper: "📄",
    portfolio: "💼",
    performance: "📈",
    ai: "✦",
    watchlist: "★",
    brokers: "🔗",
    activity: "◷",
    privacy: "🔒",
    support: "?",
    about: "ℹ",
  };
  return map[id] || "•";
}

/* ───────────────── Overview (matches reference) ───────────────── */

const OverviewSection = memo(function OverviewSection(props: {
  fullName: string;
  email: string;
  username: string;
  picture?: string | null;
  phone?: string;
  country?: string;
  memberSince: string;
  googleConnected: boolean;
  fyersConnected: boolean;
  userId: string;
  completion: { items: { label: string; done: boolean }[]; pct: number };
  portfolioValue: number;
  availableCash: number;
  invested: number;
  totalPnl: number;
  winRate: any;
  profitFactor: any;
  maxDd: any;
  maxDdAmt: any;
  closedCount: number;
  expectancy: any;
  bestTrade?: any;
  equityCurve: any[];
  holdingsPie: any[];
  holdingsCount: number;
  aiInsights: { summary: string; strengths: string[]; improve: string[]; score: number };
  activity: { when: string; activity: string; details: string; status: string }[];
  metricsLoading?: boolean;
  meLoading?: boolean;
  onEdit: () => void;
  onPassword: () => void;
  onPaper: () => void;
  onScanner: () => void;
  onAi: () => void;
  onPortfolio: () => void;
  onSettings: () => void;
}) {
  const {
    fullName,
    email,
    picture,
    phone,
    country,
    memberSince,
    googleConnected,
    fyersConnected,
    userId,
    completion,
    portfolioValue,
    availableCash,
    invested,
    totalPnl,
    winRate,
    profitFactor,
    maxDd,
    maxDdAmt,
    closedCount,
    expectancy,
    bestTrade,
    equityCurve,
    holdingsPie,
    holdingsCount,
    aiInsights,
    activity,
    metricsLoading,
  } = props;

  return (
    <div className="profile-overview animate-fade-in">
      {/* Hero header card */}
      <section className="profile-hero glass-card">
        <div className="profile-hero-left">
          <div className="profile-avatar xl">
            {picture ? <img src={picture} alt={fullName} /> : <span>{initialsFromName(fullName, email)}</span>}
          </div>
          <div className="profile-hero-meta">
            <div className="profile-name-row">
              <h2>{fullName}</h2>
              <span className="profile-verified" title="Account">
                ✓
              </span>
            </div>
            <p className="muted">
              {email}
              {phone ? `  ·  ${phone}` : ""}
            </p>
            <p className="muted profile-submeta">
              {country || "India"} · Member since {memberSince}
            </p>
            <div className="profile-chip-row">
              <span className="profile-chip plan">Free Plan</span>
              <span className="profile-chip ok">Account Active</span>
              <span className="profile-chip ok">Email Verified</span>
              {googleConnected ? <span className="profile-chip ok">Google Connected</span> : <span className="profile-chip muted-chip">Google</span>}
              {fyersConnected ? <span className="profile-chip ok">FYERS Connected</span> : <span className="profile-chip warn">FYERS Offline</span>}
            </div>
            <div className="profile-quick-btns">
              <button type="button" className="button primary-button" onClick={props.onEdit}>
                Edit Profile
              </button>
              <button type="button" className="button ghost-button" onClick={props.onPassword}>
                Change Password
              </button>
              <button type="button" className="button ghost-button" onClick={props.onScanner}>
                Run Scanner
              </button>
            </div>
          </div>
        </div>

        <div className="profile-completion glass-inset">
          <div className="profile-completion-head">
            <span>Profile Completion</span>
            <strong>{completion.pct}%</strong>
          </div>
          <div className="profile-progress-track">
            <div className="profile-progress-fill" style={{ width: `${completion.pct}%` }} />
          </div>
          <ul className="profile-checklist">
            {completion.items.map((item) => (
              <li key={item.label} className={item.done ? "done" : "todo"}>
                <span>{item.done ? "✓" : "○"}</span>
                {item.label}
              </li>
            ))}
          </ul>
        </div>

        <div className="profile-id-card glass-inset">
          <div>
            <span className="muted">User ID</span>
            <strong className="mono">{userId.slice(0, 12)}</strong>
          </div>
          <div>
            <span className="muted">Last Login</span>
            <strong>{new Date().toLocaleString()}</strong>
          </div>
          <div>
            <span className="muted">Last Active</span>
            <strong className="online">
              <i /> Online
            </strong>
          </div>
          <div className="profile-id-plan">
            <div>
              <span className="muted">Current Plan</span>
              <strong>Free Plan</strong>
            </div>
            <button type="button" className="button ghost-button" onClick={props.onSettings}>
              Manage
            </button>
          </div>
        </div>
      </section>

      {/* Status grid — profile overview hierarchy */}
      <section className="profile-status-grid" aria-label="Account status">
        <article className="glass-card profile-status-tile">
          <span className="muted">Verification</span>
          <strong>Email verified</strong>
          <span className="profile-chip ok">Active</span>
        </article>
        <article className="glass-card profile-status-tile">
          <span className="muted">Broker</span>
          <strong>{fyersConnected ? "Connected" : "Not connected"}</strong>
          <span className={`profile-chip ${fyersConnected ? "ok" : "warn"}`}>{fyersConnected ? "Live" : "Setup"}</span>
        </article>
        <article className="glass-card profile-status-tile">
          <span className="muted">2FA / Security</span>
          <strong>Sessions protected</strong>
          <button type="button" className="button ghost-button small-button" onClick={props.onPassword}>Security</button>
        </article>
        <article className="glass-card profile-status-tile">
          <span className="muted">Theme</span>
          <strong>System preference</strong>
          <button type="button" className="button ghost-button small-button" onClick={props.onSettings}>Appearance</button>
        </article>
        <article className="glass-card profile-status-tile">
          <span className="muted">Holdings</span>
          <strong>{holdingsCount}</strong>
          <button type="button" className="button ghost-button small-button" onClick={props.onPortfolio}>View</button>
        </article>
        <article className="glass-card profile-status-tile">
          <span className="muted">Open positions</span>
          <strong>{holdingsCount}</strong>
          <button type="button" className="button ghost-button small-button" onClick={props.onPaper}>Paper Desk</button>
        </article>
      </section>

      <section className="profile-quick-actions-bar glass-card" aria-label="Quick actions">
        <p className="ds-label" style={{ margin: 0 }}>Quick actions</p>
        <div className="profile-quick-btns">
          <button type="button" className="button primary-button" onClick={props.onEdit}>Edit profile</button>
          <button type="button" className="button ghost-button" onClick={props.onPassword}>Security</button>
          <button type="button" className="button ghost-button" onClick={props.onSettings}>Notifications</button>
          <button type="button" className="button ghost-button" onClick={props.onSettings}>Appearance</button>
          <button type="button" className="button ghost-button" onClick={props.onPaper}>Paper trading</button>
          <button type="button" className="button ghost-button" onClick={props.onScanner}>Run scanner</button>
        </div>
      </section>

      {/* Metric strip */}
      <section className="profile-metrics">
        {metricsLoading ? (
          <>
            <MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
            <MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
          </>
        ) : (
          <>
            <MetricCard title="Paper balance" value={money(portfolioValue)} sub={`Available ${money(availableCash)}`} icon="wallet" />
            <MetricCard title="Portfolio value" value={money(portfolioValue)} sub={`Invested ${money(invested)}`} icon="pie" />
            <MetricCard
              title="Overall P&L"
              value={money(totalPnl)}
              sub="Realized + unrealized"
              icon="trend"
              tone={totalPnl >= 0 ? "pos" : "neg"}
            />
            <MetricCard title="Win rate" value={winRate != null ? `${Number(winRate).toFixed(1)}%` : "—"} sub={`${closedCount} closed trades`} icon="target" />
            <MetricCard title="Profit factor" value={profitFactor != null ? Number(profitFactor).toFixed(2) : "—"} sub={`Expectancy ${expectancy != null ? money(Number(expectancy)) : "—"}`} icon="bars" />
            <MetricCard
              title="Max drawdown"
              value={maxDd != null ? `${Number(maxDd).toFixed(1)}%` : money(maxDdAmt)}
              sub="Peak to trough"
              icon="shield"
              tone="neg"
            />
          </>
        )}
      </section>

      {/* Charts row — lazy recharts */}
      <section className="profile-charts-row">
        <div className="glass-card profile-chart-card">
          <div className="profile-card-head">
            <h3>Performance Overview</h3>
            <span className="helper-chip">All time</span>
          </div>
          <div className="profile-chart-body">
            {metricsLoading ? (
              <ChartSkeleton height={220} />
            ) : (
              <Suspense fallback={<ChartSkeleton height={220} />}>
                <LazyEquityChart data={equityCurve} height={220} />
              </Suspense>
            )}
          </div>
          <div className="profile-stat-row">
            <div>
              <span className="muted">Best trade</span>
              <strong className="pos">{metricsLoading ? "…" : money(bestTrade)}</strong>
            </div>
            <div>
              <span className="muted">Trades</span>
              <strong>{metricsLoading ? "…" : closedCount}</strong>
            </div>
            <div>
              <span className="muted">Open</span>
              <strong>{metricsLoading ? "…" : holdingsCount}</strong>
            </div>
          </div>
        </div>

        <div className="glass-card profile-chart-card">
          <div className="profile-card-head">
            <h3>Holdings Summary</h3>
          </div>
          {metricsLoading ? (
            <ChartSkeleton height={180} />
          ) : (
            <Suspense fallback={<ChartSkeleton height={180} />}>
              <LazyHoldingsPie data={holdingsPie} height={180} centerLabel={{ value: holdingsCount, sub: "Open" }} />
            </Suspense>
          )}
          <ul className="profile-legend">
            {(metricsLoading ? [] : holdingsPie).map((h, i) => (
              <li key={h.name}>
                <i style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                {h.name}
                <span>{h.value}%</span>
              </li>
            ))}
          </ul>
          <button type="button" className="button ghost-button full" onClick={props.onPortfolio}>
            View Portfolio
          </button>
        </div>

        <div className="glass-card profile-chart-card ai-card">
          <div className="profile-card-head">
            <h3>
              AI Trading Coach <span className="profile-badge-new">New</span>
            </h3>
          </div>
          <div className="ai-hero">
            <div className="ai-brain">✦</div>
            <div>
              <strong>Discipline score {aiInsights.score}</strong>
              <p>{aiInsights.summary}</p>
            </div>
          </div>
          <div className="ai-two-col">
            <div>
              <h4 className="pos">Strengths</h4>
              <ul>
                {aiInsights.strengths.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="neg">Areas to Improve</h4>
              <ul>
                {aiInsights.improve.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          </div>
          <button type="button" className="button primary-button full" onClick={props.onAi}>
            View Full Analysis
          </button>
        </div>
      </section>

      {/* Bottom row */}
      <section className="profile-bottom-row">
        <div className="glass-card">
          <div className="profile-card-head">
            <h3>Recent Activity</h3>
          </div>
          <div className="table-scroll">
            <table className="profile-table">
              <thead>
                <tr>
                  <th>Date & Time</th>
                  <th>Activity</th>
                  <th>Details</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {activity.map((row, idx) => (
                  <tr key={idx}>
                    <td>{row.when}</td>
                    <td>{row.activity}</td>
                    <td className="muted">{row.details}</td>
                    <td>
                      <span className={`status-pill ${row.status === "Success" ? "ok" : row.status === "Loss" ? "bad" : ""}`}>
                        {row.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="glass-card profile-actions-card">
          <div className="profile-card-head">
            <h3>Quick Actions</h3>
          </div>
          <div className="profile-action-grid">
            <button type="button" className="profile-action" onClick={props.onPaper}>
              <span>📄</span> Paper Trading
            </button>
            <button type="button" className="profile-action" onClick={props.onScanner}>
              <span>📡</span> Run Scanner
            </button>
            <button type="button" className="profile-action" onClick={props.onEdit}>
              <span>✎</span> Edit Profile
            </button>
            <button type="button" className="profile-action" onClick={props.onSettings}>
              <span>⚙</span> Account Settings
            </button>
          </div>
        </div>
      </section>
    </div>
  );
});

const MetricCard = memo(function MetricCard({
  title,
  value,
  sub,
  tone,
}: {
  title: string;
  value: string;
  sub: string;
  icon?: string;
  tone?: "pos" | "neg";
}) {
  return (
    <article className="glass-card metric-tile-card">
      <span className="muted">{title}</span>
      <strong className={tone === "pos" ? "pos" : tone === "neg" ? "neg" : ""}>{value}</strong>
      <span className="muted sub">{sub}</span>
    </article>
  );
});

/* ───────────────── Other sections ───────────────── */

/**
 * Editable personal form with local draft state.
 * Parent `savedPrefs` only seeds the draft — typing never depends on parent re-fetches.
 */
function PersonalSection({
  savedPrefs,
  fullName,
  email,
  saving,
  onDirtyChange,
  onSaved,
}: {
  savedPrefs: ProfilePreferences;
  fullName: string;
  email: string;
  saving?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
  onSaved: (next: ProfilePreferences) => boolean | Promise<boolean>;
}) {
  const baselineRef = useRef<ProfilePreferences>(savedPrefs);
  const [draft, setDraft] = useState<ProfilePreferences>(() => ({ ...savedPrefs }));
  const [baseline, setBaseline] = useState<ProfilePreferences>(() => ({ ...savedPrefs }));

  // Seed once when parent first delivers server prefs (empty → filled). Never while dirty.
  useEffect(() => {
    const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
    if (dirty) return;
    // Only re-seed if savedPrefs actually changed from our baseline
    if (JSON.stringify(savedPrefs) === JSON.stringify(baselineRef.current)) return;
    baselineRef.current = savedPrefs;
    setBaseline(savedPrefs);
    setDraft(savedPrefs);
    onDirtyChange?.(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional seed when savedPrefs identity content changes while clean
  }, [savedPrefs]);

  const dirty = useMemo(
    () => JSON.stringify(draft) !== JSON.stringify(baseline),
    [draft, baseline],
  );

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const setField = useCallback((k: keyof ProfilePreferences, v: string) => {
    setDraft((prev) => ({ ...prev, [k]: v }));
  }, []);

  const handleCancel = useCallback(() => {
    setDraft(baseline);
    onDirtyChange?.(false);
  }, [baseline, onDirtyChange]);

  const handleSave = useCallback(async () => {
    const ok = await onSaved(draft);
    if (!ok) {
      // Keep draft editable with user changes intact
      return;
    }
    setBaseline(draft);
    baselineRef.current = draft;
    onDirtyChange?.(false);
  }, [draft, onSaved, onDirtyChange]);

  return (
    <section className="glass-card profile-form-card animate-fade-in" data-testid="personal-info-form">
      <h2>Personal Information</h2>
      <p className="muted">
        Account email is read-only. All other fields save to your account and sync across devices.
      </p>
      <div className="profile-form-grid">
        <Field label="Full name (account)" value={fullName} readOnly />
        <Field label="Email (account)" value={email} readOnly />
        <Field
          label="Display name"
          value={draft.displayName || ""}
          onChange={(v) => setField("displayName", v)}
          autoComplete="nickname"
        />
        <Field
          label="Username"
          value={draft.username || ""}
          onChange={(v) => setField("username", v)}
          autoComplete="username"
        />
        <Field
          label="Phone"
          value={draft.phone || ""}
          onChange={(v) => setField("phone", v)}
          autoComplete="tel"
          inputMode="tel"
        />
        <Field
          label="Country"
          value={draft.country || ""}
          onChange={(v) => setField("country", v)}
          autoComplete="country-name"
        />
        <Field
          label="State"
          value={draft.state || ""}
          onChange={(v) => setField("state", v)}
          autoComplete="address-level1"
        />
        <Field
          label="City"
          value={draft.city || ""}
          onChange={(v) => setField("city", v)}
          autoComplete="address-level2"
        />
        <Field label="Language" value={draft.language || ""} onChange={(v) => setField("language", v)} />
        <Field label="Currency" value={draft.currency || ""} onChange={(v) => setField("currency", v)} />
        <Field label="Timezone" value={draft.timezone || ""} onChange={(v) => setField("timezone", v)} />
        <Field
          label="Postal code"
          value={draft.postalCode || ""}
          onChange={(v) => setField("postalCode", v)}
          autoComplete="postal-code"
        />
        <Field
          label="Address"
          value={draft.address || ""}
          onChange={(v) => setField("address", v)}
          className="full"
          autoComplete="street-address"
        />
        <Field
          label="Bio"
          value={draft.bio || ""}
          onChange={(v) => setField("bio", v)}
          className="full"
          multiline
        />
      </div>
      <div className="profile-form-actions">
        <button
          type="button"
          className="button ghost-button"
          onClick={handleCancel}
          disabled={!dirty || saving}
        >
          Cancel
        </button>
        <button
          type="button"
          className="button primary-button"
          onClick={() => void handleSave()}
          disabled={!dirty || saving}
          data-testid="personal-save"
        >
          {saving ? "Saving…" : "Save Changes"}
        </button>
      </div>
      {dirty ? <p className="muted" style={{ marginTop: 8 }}>You have unsaved changes.</p> : null}
    </section>
  );
}

function Field({
  label,
  value,
  onChange,
  readOnly,
  className = "",
  autoComplete,
  inputMode,
  multiline,
}: {
  label: string;
  value: string;
  onChange?: (v: string) => void;
  readOnly?: boolean;
  className?: string;
  autoComplete?: string;
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"];
  multiline?: boolean;
}) {
  const id = useId();
  return (
    <label className={`profile-field ${className}`} htmlFor={id}>
      <span>{label}</span>
      {multiline ? (
        <textarea
          id={id}
          value={value}
          readOnly={readOnly}
          disabled={readOnly}
          onChange={(e) => onChange?.(e.target.value)}
          rows={3}
          className="profile-input"
        />
      ) : (
        <input
          id={id}
          type="text"
          value={value}
          readOnly={!!readOnly}
          disabled={false}
          onChange={(e) => {
            if (!readOnly) onChange?.(e.target.value);
          }}
          autoComplete={autoComplete}
          inputMode={inputMode}
          className="profile-input"
        />
      )}
    </label>
  );
}

function SecuritySection({ email, googleConnected }: { email: string; googleConnected: boolean }) {
  return (
    <div className="profile-stack animate-fade-in">
      <section className="glass-card">
        <h2>Password</h2>
        <p className="muted">
          Logged-in password change uses the secure reset flow. Request a reset link for <strong>{email}</strong> from the login page (Forgot Password), or sign out and use Forgot Password.
        </p>
        <a className="button ghost-button" href="/auth/forgot-password">
          Open Forgot Password
        </a>
      </section>
      <section className="glass-card">
        <h2>Google Login</h2>
        <p>
          Status:{" "}
          <strong className={googleConnected ? "pos" : ""}>{googleConnected ? "Connected" : "Not connected via Google"}</strong>
        </p>
        <p className="muted">Google linking is managed at login. Email/password accounts can use Google Sign-In if the email matches.</p>
      </section>
      <section className="glass-card">
        <h2>Two-Factor Authentication</h2>
        <p className="muted">2FA (Authenticator / Email OTP) is planned. OTP infrastructure exists server-side; enablement UI will attach here.</p>
        <span className="profile-chip muted-chip">Not enabled</span>
      </section>
      <section className="glass-card">
        <h2>Active Sessions</h2>
        <Suspense fallback={<ChartSkeleton height={120} />}>
          <LazySettingsSessions />
        </Suspense>
      </section>
    </div>
  );
}

function PreferencesSection({
  prefs,
  theme,
  onTheme,
  onChange,
  onSave,
}: {
  prefs: ProfilePreferences;
  theme: string;
  onTheme: (t: "dark" | "light") => void;
  onChange: (p: ProfilePreferences) => void;
  onSave: () => void;
}) {
  return (
    <section className="glass-card profile-form-card animate-fade-in">
      <h2>Trading Preferences</h2>
      <div className="profile-form-grid">
        <label className="profile-field">
          <span>Theme</span>
          <select
            value={theme}
            onChange={(e) => {
              const v = e.target.value as "dark" | "light";
              onTheme(v);
              onChange({ ...prefs, themePreference: v });
            }}
          >
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </label>
        <label className="profile-field">
          <span>Scanner mode</span>
          <select value={prefs.scannerMode} onChange={(e) => onChange({ ...prefs, scannerMode: e.target.value as any })}>
            <option value="swing">Swing</option>
            <option value="intraday">Intraday</option>
            <option value="positional">Positional</option>
          </select>
        </label>
        <label className="profile-field">
          <span>Default timeframe</span>
          <select value={prefs.defaultTimeframe} onChange={(e) => onChange({ ...prefs, defaultTimeframe: e.target.value })}>
            <option value="1d">1D</option>
            <option value="4h">4H</option>
            <option value="1h">1H</option>
            <option value="1W">1W</option>
          </select>
        </label>
        <label className="profile-field">
          <span>Default universe</span>
          <select value={prefs.defaultUniverse} onChange={(e) => onChange({ ...prefs, defaultUniverse: e.target.value })}>
            <option value="NIFTY50">Nifty50</option>
            <option value="NIFTY100">Nifty100</option>
            <option value="NIFTY500">Nifty500</option>
          </select>
        </label>
        <label className="profile-field">
          <span>Dashboard layout</span>
          <select value={prefs.dashboardLayout} onChange={(e) => onChange({ ...prefs, dashboardLayout: e.target.value as any })}>
            <option value="comfortable">Comfortable</option>
            <option value="compact">Compact</option>
          </select>
        </label>
        <Field label="Language" value={prefs.language || ""} onChange={(v) => onChange({ ...prefs, language: v })} />
        <Field label="Currency" value={prefs.currency || ""} onChange={(v) => onChange({ ...prefs, currency: v })} />
        <Field label="Timezone" value={prefs.timezone || ""} onChange={(v) => onChange({ ...prefs, timezone: v })} />
      </div>
      <div className="profile-form-actions">
        <button type="button" className="button primary-button" onClick={onSave}>
          Save Preferences
        </button>
      </div>
    </section>
  );
}

function NotificationsSection({
  prefs,
  onChange,
  onSave,
}: {
  prefs: ProfilePreferences;
  onChange: (n: NonNullable<ProfilePreferences["notifications"]>) => void;
  onSave: () => void;
}) {
  const n = prefs.notifications!;
  const toggle = (k: keyof typeof n) => onChange({ ...n, [k]: !n[k] });
  const rows: { key: keyof typeof n; label: string }[] = [
    { key: "email", label: "Email notifications" },
    { key: "browser", label: "Browser notifications" },
    { key: "scanner", label: "Scanner complete" },
    { key: "priceAlerts", label: "Price alerts" },
    { key: "portfolioAlerts", label: "Portfolio alerts" },
    { key: "weeklyReport", label: "Weekly report" },
    { key: "monthlyReport", label: "Monthly report" },
  ];
  return (
    <section className="glass-card animate-fade-in">
      <h2>Notifications</h2>
      <p className="muted">Preferences are stored on this device and applied when notification delivery is configured.</p>
      <ul className="profile-toggle-list">
        {rows.map((r) => (
          <li key={r.key}>
            <span>{r.label}</span>
            <button type="button" className={`profile-toggle ${n[r.key] ? "on" : ""}`} onClick={() => toggle(r.key)} aria-pressed={n[r.key]}>
              <i />
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="button primary-button" onClick={onSave}>
        Save
      </button>
    </section>
  );
}

function PaperPerfSection({
  mode,
  account,
  analytics,
  positions,
  equityCurve,
  holdingsPie,
  onNavigatePaper,
}: any) {
  return (
    <div className="profile-stack animate-fade-in">
      <div className="profile-metrics">
        <MetricCard title="Portfolio Value" value={money(account?.equity)} sub={`Cash ${money(account?.available_cash ?? account?.balance)}`} />
        <MetricCard title="Invested" value={money(account?.total_invested)} sub={`Open ${positions?.length || 0}`} />
        <MetricCard title="Realized P&L" value={money(account?.realized_pnl)} sub={`Unrealized ${money(account?.unrealized_pnl)}`} tone={Number(account?.realized_pnl || 0) >= 0 ? "pos" : "neg"} />
        <MetricCard title="Win Rate" value={analytics?.win_rate_pct != null ? `${analytics.win_rate_pct}%` : "—"} sub={`PF ${analytics?.profit_factor ?? "—"}`} />
        <MetricCard title="Max DD" value={analytics?.max_drawdown_pct != null ? `${analytics.max_drawdown_pct}%` : money(analytics?.max_drawdown)} sub={`Trades ${analytics?.total_trades ?? 0}`} tone="neg" />
        <MetricCard title="Streak" value={`${analytics?.current_streak_type || "none"} ${analytics?.current_streak_count || 0}`} sub="Current" />
      </div>
      {(mode === "performance" || mode === "paper") && (
        <div className="glass-card">
          <h3>Equity Curve</h3>
          <Suspense fallback={<ChartSkeleton height={260} />}>
            <LazyEquityChart data={equityCurve} height={260} showAxes />
          </Suspense>
        </div>
      )}
      {(mode === "portfolio" || mode === "paper") && (
        <div className="glass-card">
          <h3>Open Positions</h3>
          {positions?.length ? (
            <div className="table-scroll">
              <table className="profile-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Avg</th>
                    <th>LTP</th>
                    <th>P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p: any) => (
                    <tr key={p.id || p.symbol}>
                      <td>{p.symbol}</td>
                      <td>{p.qty}</td>
                      <td>{money(p.avg_entry_price ?? p.average_price)}</td>
                      <td>{money(p.current_price)}</td>
                      <td className={Number(p.unrealized_pnl) >= 0 ? "pos" : "neg"}>{money(p.unrealized_pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="muted">No open positions.</p>
          )}
          <button type="button" className="button primary-button" style={{ marginTop: 12 }} onClick={onNavigatePaper}>
            Open Paper Trading
          </button>
        </div>
      )}
      {mode === "portfolio" && (
        <div className="glass-card">
          <h3>Allocation</h3>
          <Suspense fallback={<ChartSkeleton height={200} />}>
            <LazyHoldingsPie data={holdingsPie} height={200} />
          </Suspense>
        </div>
      )}
    </div>
  );
}

function AiSection({ insights, analytics }: any) {
  return (
    <section className="glass-card ai-card animate-fade-in">
      <h2>
        AI Trading Coach <span className="profile-badge-new">New</span>
      </h2>
      <p className="ai-lead">{insights.summary}</p>
      <div className="profile-metrics">
        <MetricCard title="Discipline Score" value={String(insights.score)} sub="Heuristic from your paper stats" />
        <MetricCard title="Win Rate" value={analytics?.win_rate_pct != null ? `${analytics.win_rate_pct}%` : "—"} sub="Closed trades" />
        <MetricCard title="Profit Factor" value={analytics?.profit_factor != null ? String(analytics.profit_factor) : "—"} sub="Gross wins / losses" />
      </div>
      <div className="ai-two-col">
        <div>
          <h4 className="pos">Strengths</h4>
          <ul>
            {insights.strengths.map((s: string) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="neg">Weaknesses / Suggestions</h4>
          <ul>
            {insights.improve.map((s: string) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </div>
      </div>
      <p className="muted" style={{ marginTop: 16 }}>
        Insights are generated from your existing paper-trading analytics only. Numbers are never invented. Connect FYERS and trade consistently for richer coaching.
      </p>
    </section>
  );
}

function WatchlistSection({ prefs, onSave }: { prefs: ProfilePreferences; onSave: (list: string[]) => void }) {
  const [symbol, setSymbol] = useState("");
  const list = prefs.watchlist || [];
  return (
    <section className="glass-card animate-fade-in">
      <h2>Watchlist</h2>
      <div className="profile-watch-add">
        <input placeholder="Symbol e.g. RELIANCE" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
        <button
          type="button"
          className="button primary-button"
          onClick={() => {
            const s = symbol.trim().toUpperCase();
            if (!s || list.includes(s)) return;
            onSave([...list, s]);
            setSymbol("");
          }}
        >
          Add
        </button>
      </div>
      <ul className="profile-watch-list">
        {list.map((s) => (
          <li key={s}>
            <strong>{s}</strong>
            <button type="button" className="button ghost-button" onClick={() => onSave(list.filter((x) => x !== s))}>
              Remove
            </button>
          </li>
        ))}
        {!list.length ? <li className="muted">No favourites yet.</li> : null}
      </ul>
    </section>
  );
}

function BrokersSection({ fyersConnected, token }: { fyersConnected: boolean; token: any }) {
  return (
    <div className="profile-broker-grid animate-fade-in">
      <article className="glass-card">
        <h3>FYERS</h3>
        <p className={fyersConnected ? "pos" : "neg"}>{fyersConnected ? "Connected" : "Not connected"}</p>
        <p className="muted">Status: {token?.status || token?.message || "unknown"}</p>
        <p className="muted">Manage token from Paper Desk → Capital → Broker Access Token. Existing broker APIs are reused.</p>
      </article>
      {["Upstox", "Zerodha", "Angel One"].map((name) => (
        <article key={name} className="glass-card muted-card">
          <h3>{name}</h3>
          <span className="profile-chip muted-chip">Coming soon</span>
          <p className="muted">Future-ready connector slot.</p>
        </article>
      ))}
    </div>
  );
}

function ActivitySection({ activity }: { activity: any[] }) {
  return (
    <section className="glass-card animate-fade-in">
      <h2>Activity History</h2>
      <div className="table-scroll">
        <table className="profile-table">
          <thead>
            <tr>
              <th>When</th>
              <th>Activity</th>
              <th>Details</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {activity.map((row, i) => (
              <tr key={i}>
                <td>{row.when}</td>
                <td>{row.activity}</td>
                <td>{row.details}</td>
                <td>{row.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PrivacySection() {
  return (
    <section className="glass-card animate-fade-in">
      <h2>Privacy</h2>
      <ul className="profile-link-list">
        <li>Download account data — export from browser storage + paper APIs (coming server-side pack)</li>
        <li>Deactivate account — contact support; server supports soft-delete field</li>
        <li>Delete account — irreversible; requires admin/support workflow</li>
      </ul>
    </section>
  );
}

function SupportSection() {
  return (
    <section className="glass-card animate-fade-in">
      <h2>Support</h2>
      <ul className="profile-link-list">
        <li>
          <a href="https://github.com" target="_blank" rel="noreferrer">
            Documentation
          </a>
        </li>
        <li>FAQ — scanner, paper trading, FYERS token</li>
        <li>Report bug / Feature request — via your team channel</li>
      </ul>
    </section>
  );
}

function AboutSection({ health }: { health: any }) {
  return (
    <section className="glass-card animate-fade-in">
      <h2>About</h2>
      <div className="profile-form-grid">
        <MetricCard title="Frontend" value="0.1.0" sub="Vite + React" />
        <MetricCard title="API" value={health?.status || "unknown"} sub="Backend health" />
        <MetricCard
          title="Services"
          value={String(health?.services?.length ?? "—")}
          sub="Reported components"
        />
      </div>
      <p className="muted" style={{ marginTop: 12 }}>
        Trading System — advisory paper trading & swing research platform.
      </p>
    </section>
  );
}

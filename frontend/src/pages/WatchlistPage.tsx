import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { fetchUserProfile, patchUserProfile } from "../api";
import {
  cacheProfilePrefs,
  loadProfilePrefs,
  profileFromApi,
  type ProfilePreferences,
} from "../utils/profilePrefs";
import { Card, CardHeader, EmptyState, Button, ConfirmDialog, useToast } from "../design-system";

export function WatchlistPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [prefs, setPrefs] = useState<ProfilePreferences>(() => loadProfilePrefs(user?.id));
  const [loading, setLoading] = useState(true);
  const [confirmClear, setConfirmClear] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");

  const watchlist = prefs.watchlist ?? [];

  const sorted = useMemo(
    () => [...watchlist].sort((a, b) => a.localeCompare(b)),
    [watchlist],
  );

  const load = useCallback(async () => {
    if (!user?.id) {
      setLoading(false);
      return;
    }
    try {
      const api = await fetchUserProfile({ force: true });
      const mapped = profileFromApi(api);
      setPrefs(mapped);
      cacheProfilePrefs(user.id, mapped);
    } catch (e: any) {
      toast.error("Could not load watchlist", e?.message);
    } finally {
      setLoading(false);
    }
  }, [user?.id, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  async function persist(nextList: string[]) {
    if (!user?.id) {
      toast.warning("Sign in to save your watchlist to your account.");
      return;
    }
    const previous = prefs;
    const next = { ...prefs, watchlist: nextList };
    setPrefs(next); // optimistic
    try {
      const updated = await patchUserProfile({
        preferences: { watchlist: nextList },
      });
      const mapped = profileFromApi(updated);
      setPrefs(mapped);
      cacheProfilePrefs(user.id, mapped);
    } catch (e: any) {
      setPrefs(previous);
      toast.error("Could not save watchlist", e?.message);
    }
  }

  function addSymbol() {
    const sym = newSymbol.trim().toUpperCase().replace(/\s+/g, "");
    if (!sym) return;
    if (watchlist.includes(sym)) {
      toast.info(`${sym} is already in your favorites.`);
      return;
    }
    void persist([...watchlist, sym]).then(() => {
      setNewSymbol("");
      toast.success(`Added ${sym} to favorites`);
    });
  }

  function removeSymbol(sym: string) {
    void persist(watchlist.filter((s) => s !== sym)).then(() => toast.info(`Removed ${sym}`));
  }

  return (
    <div className="page-container">
      <header className="page-hero">
        <div>
          <p className="ds-label">Watchlist</p>
          <h1 className="ds-display">Favorites</h1>
          <p className="ds-muted">
            Track symbols you care about. Saved to your account — available on every device.
          </p>
        </div>
        <div className="page-hero__actions">
          <Button variant="trade" onClick={() => navigate("/scanner")}>
            TRADE
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader label="Add symbol" title="Build your list" />
        <form
          className="watchlist-add-form"
          onSubmit={(e) => {
            e.preventDefault();
            addSymbol();
          }}
        >
          <input
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            placeholder="e.g. RELIANCE"
            aria-label="Symbol to add"
            maxLength={24}
          />
          <Button type="submit" variant="secondary">
            Add
          </Button>
        </form>
      </Card>

      <Card>
        <CardHeader
          label="Your favorites"
          title={loading ? "Loading…" : `${sorted.length} symbol${sorted.length === 1 ? "" : "s"}`}
          actions={
            sorted.length > 0 ? (
              <Button variant="ghost" size="sm" onClick={() => setConfirmClear(true)}>
                Clear all
              </Button>
            ) : null
          }
        />
        {sorted.length === 0 && !loading ? (
          <EmptyState
            title="No watchlist"
            description="Add NSE symbols you want to follow, or star them from scanner results."
            primaryAction={{ label: "Open Scanner", onClick: () => navigate("/scanner"), variant: "trade" }}
            secondaryAction={{ label: "Paper Desk", onClick: () => navigate("/paper"), variant: "ghost" }}
          />
        ) : (
          <ul className="markets-symbol-list watchlist-list">
            {sorted.map((sym) => (
              <li key={sym}>
                <div className="markets-symbol-row">
                  <button
                    type="button"
                    className="watchlist-sym-btn"
                    onClick={() => navigate(`/scanner?symbol=${encodeURIComponent(sym)}`)}
                  >
                    <strong>{sym}</strong>
                    <span className="ds-caption">Open in scanner</span>
                  </button>
                  <div className="watchlist-row-actions">
                    <Button variant="buy" size="sm" onClick={() => navigate(`/paper?symbol=${sym}&side=BUY`)}>
                      BUY
                    </Button>
                    <Button variant="sell" size="sm" onClick={() => navigate(`/paper?symbol=${sym}&side=SELL`)}>
                      SELL
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => removeSymbol(sym)} aria-label={`Remove ${sym}`}>
                      Remove
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ConfirmDialog
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        onConfirm={() => {
          void persist([]).then(() => {
            setConfirmClear(false);
            toast.success("Watchlist cleared");
          });
        }}
        title="Clear watchlist?"
        description="This removes all favorites from your account. You can add symbols again anytime."
        confirmLabel="Clear all"
        tone="danger"
      />
    </div>
  );
}

export default WatchlistPage;

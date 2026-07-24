import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { fetchUserProfile, patchUserProfile } from "../api";
import {
  cacheProfilePrefs,
  loadProfilePrefs,
  profileFromApi,
  type ProfilePreferences,
} from "../utils/profilePrefs";
import { useToast, Button, EmptyState } from "../design-system";
import { ListSkeleton } from "./Skeleton";
import { ConfirmDialog } from "../design-system";

export function WatchlistTab() {
  const { user } = useAuth();
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
    setPrefs(next);
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

  function handleBuy(sym: string) {
    window.dispatchEvent(
      new CustomEvent("paper:open-order", {
        detail: { symbol: sym, side: "BUY", returnTo: "/paper" },
      }),
    );
  }

  return (
    <section>
      <div className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Favorites</p>
            <h2>Watchlist</h2>
          </div>
          {sorted.length > 0 ? (
            <Button variant="ghost" size="sm" onClick={() => setConfirmClear(true)}>
              Clear all
            </Button>
          ) : null}
        </div>

        <form
          className="watchlist-add-form"
          onSubmit={(e) => {
            e.preventDefault();
            addSymbol();
          }}
          style={{ marginBottom: 12, display: "flex", gap: 8 }}
        >
          <input
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            placeholder="e.g. RELIANCE"
            aria-label="Symbol to add"
            maxLength={24}
            style={{ flex: 1 }}
          />
          <Button type="submit" variant="secondary">
            Add
          </Button>
        </form>

        {loading ? (
          <ListSkeleton items={5} />
        ) : sorted.length === 0 ? (
          <EmptyState
            title="No watchlist"
            description="Add NSE symbols you want to follow, or star them from scanner results."
          />
        ) : (
          <div className="table-scroll">
            <table className="candidate-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Scanner Score</th>
                  <th>Confidence</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((sym) => (
                  <tr key={sym}>
                    <td>
                      <strong>{sym}</strong>
                    </td>
                    <td className="number-cell">--</td>
                    <td className="number-cell">--</td>
                    <td>
                      <div style={{ display: "flex", gap: 8 }}>
                        <Button variant="buy" size="sm" onClick={() => handleBuy(sym)}>
                          BUY
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => removeSymbol(sym)} aria-label={`Remove ${sym}`}>
                          Remove
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

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
    </section>
  );
}

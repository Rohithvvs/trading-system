import { useMemo, useState } from "react";
import { useToast, Button, EmptyState, ConfirmDialog } from "../design-system";

const WATCHLIST_STORAGE_KEY = "user_watchlist";

function getLocalWatchlist(): string[] {
  try {
    const raw = localStorage.getItem(WATCHLIST_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function setLocalWatchlist(symbols: string[]) {
  try {
    localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify(symbols));
  } catch {
    /* ignore */
  }
}

export function WatchlistTab() {
  const toast = useToast();
  const [watchlist, setWatchlist] = useState<string[]>(() => getLocalWatchlist());
  const [confirmClear, setConfirmClear] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");

  const sorted = useMemo(
    () => [...watchlist].sort((a, b) => a.localeCompare(b)),
    [watchlist],
  );

  function updateWatchlist(nextList: string[]) {
    setWatchlist(nextList);
    setLocalWatchlist(nextList);
  }

  function addSymbol() {
    const sym = newSymbol.trim().toUpperCase().replace(/\s+/g, "");
    if (!sym) return;
    if (watchlist.includes(sym)) {
      toast.info(`${sym} is already in your favorites.`);
      return;
    }
    updateWatchlist([...watchlist, sym]);
    setNewSymbol("");
    toast.success(`Added ${sym} to favorites`);
  }

  function removeSymbol(sym: string) {
    updateWatchlist(watchlist.filter((s) => s !== sym));
    toast.info(`Removed ${sym}`);
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

        {sorted.length === 0 ? (
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
          updateWatchlist([]);
          setConfirmClear(false);
          toast.success("Watchlist cleared");
        }}
        title="Clear watchlist?"
        description="This removes all favorites. You can add symbols again anytime."
        confirmLabel="Clear all"
        tone="danger"
      />
    </section>
  );
}

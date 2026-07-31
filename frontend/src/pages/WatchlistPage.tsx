import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardHeader, EmptyState, Button, ConfirmDialog, useToast } from "../design-system";

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

export function WatchlistPage() {
  const navigate = useNavigate();
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

  return (
    <div className="page-container">
      <header className="page-hero">
        <div>
          <p className="ds-label">Watchlist</p>
          <h1 className="ds-display">Favorites</h1>
          <p className="ds-muted">
            Track symbols you care about.
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
          title={`${sorted.length} symbol${sorted.length === 1 ? "" : "s"}`}
          actions={
            sorted.length > 0 ? (
              <Button variant="ghost" size="sm" onClick={() => setConfirmClear(true)}>
                Clear all
              </Button>
            ) : null
          }
        />
        {sorted.length === 0 ? (
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
                    <Button
                      variant="buy"
                      size="sm"
                      onClick={() => {
                        navigate(`/paper-order?symbol=${encodeURIComponent(sym)}&side=BUY`, {
                          state: {
                            symbol: sym,
                            side: "BUY",
                            returnTo: "/watchlist",
                          },
                        });
                      }}
                    >
                      BUY
                    </Button>
                    <Button
                      variant="sell"
                      size="sm"
                      onClick={() => {
                        navigate(`/paper-order?symbol=${encodeURIComponent(sym)}&side=SELL`, {
                          state: {
                            symbol: sym,
                            side: "SELL",
                            returnTo: "/watchlist",
                          },
                        });
                      }}
                    >
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
          updateWatchlist([]);
          setConfirmClear(false);
          toast.success("Watchlist cleared");
        }}
        title="Clear watchlist?"
        description="This removes all favorites. You can add symbols again anytime."
        confirmLabel="Clear all"
        tone="danger"
      />
    </div>
  );
}

export default WatchlistPage;

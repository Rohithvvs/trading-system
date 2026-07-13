import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createWorkstationAlert,
  deleteScannerPreset,
  deleteWorkstationAlert,
  fetchMarketOverview,
  fetchSavedScans,
  fetchWorkstationAlerts,
  getLatestScan,
  fetchUserProfile,
} from "../api";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import { MetricCardSkeleton, ListSkeleton } from "../components/Skeleton";
import { Card, CardHeader, EmptyState, Button, PnL, StatusPill } from "../design-system";
import { useAuth } from "../hooks/useAuth";
import type { ProfilePreferences } from "../utils/profilePrefs";

type Props = {
  onLoadSavedScan?: (scan: any) => void;
};

const FRESH_MS = 60_000;

function isFresh(key: string): boolean {
  // soft freshness: if we have cached data, paint immediately and revalidate
  return !!getCached(key);
}

/**
 * Retail Markets home — cache-first paint, progressive refresh, memoized sections.
 */
export const MarketsPage = memo(function MarketsPage({ onLoadSavedScan }: Props) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [market, setMarket] = useState<any | null>(() => getCached(CACHE_KEYS.marketOverview));
  const [savedScans, setSavedScans] = useState<any[]>(() => getCached(CACHE_KEYS.savedScans) || []);
  const [alerts, setAlerts] = useState<any[]>(() => getCached(CACHE_KEYS.workstationAlerts) || []);
  const [latestScan, setLatestScan] = useState<any | null>(() => getCached(`${CACHE_KEYS.latestScan}:scanner`));
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Only block UI if we have nothing cached for market
  const [loading, setLoading] = useState(() => !getCached(CACHE_KEYS.marketOverview));
  const [refreshing, setRefreshing] = useState(false);
  const [priceAlert, setPriceAlert] = useState({ name: "", symbol: "", condition: ">=", target_price: "" });
  const mounted = useRef(true);
  const lastLoadAt = useRef(0);

  const load = useCallback(async (force = false) => {
    const now = Date.now();
    // Debounce accidental double mounts (StrictMode) within 800ms
    if (!force && now - lastLoadAt.current < 800) return;
    lastLoadAt.current = now;

    const hasCache = isFresh(CACHE_KEYS.marketOverview);
    if (hasCache) {
      setRefreshing(true);
      setLoading(false);
    } else {
      setLoading(true);
    }

    try {
      // Wave 1 (critical path): market + scan — paint KPIs ASAP
      const [marketData, latestData] = await Promise.all([
        fetchMarketOverview().catch(() => null),
        getLatestScan().catch(() => null),
      ]);
      if (!mounted.current) return;
      if (marketData) setMarket(marketData);
      if (latestData) setLatestScan(latestData);
      setLoading(false);

      // Wave 2 (secondary): scans, alerts, profile watchlist — non-blocking
      const [savedData, alertsData, profile] = await Promise.all([
        fetchSavedScans().catch(() => []),
        fetchWorkstationAlerts().catch(() => []),
        user?.id
          ? fetchUserProfile().catch(() => null)
          : Promise.resolve(null),
      ]);
      if (!mounted.current) return;
      setSavedScans(savedData || []);
      setAlerts(alertsData || []);
      if (profile?.preferences?.watchlist) {
        setWatchlist(profile.preferences.watchlist);
      } else if (profile?.watchlist) {
        setWatchlist(profile.watchlist);
      }
    } catch (err) {
      if (!mounted.current) return;
      setError(err instanceof Error ? err.message : "Failed to load markets.");
    } finally {
      if (mounted.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [user?.id]);

  useEffect(() => {
    mounted.current = true;
    void load(false);
    return () => {
      mounted.current = false;
    };
  }, [load]);

  const handleCreatePriceAlert = useCallback(async () => {
    if (!priceAlert.symbol || !priceAlert.target_price) return;
    await createWorkstationAlert({
      alert_type: "PRICE",
      name: priceAlert.name || `${priceAlert.symbol} price alert`,
      symbol: priceAlert.symbol,
      condition: priceAlert.condition,
      target_price: Number(priceAlert.target_price),
    });
    setPriceAlert({ name: "", symbol: "", condition: ">=", target_price: "" });
    await load(true);
  }, [priceAlert, load]);

  const buyCandidates = latestScan?.buy_candidates ?? [];
  const watchCandidates = latestScan?.watch_candidates ?? [];
  const highlights = useMemo(
    () => [...buyCandidates, ...watchCandidates].slice(0, 8),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [latestScan],
  );
  const lastScanDate = useMemo(() => {
    if (!latestScan?.last_scan_completed_at) return null;
    return new Date(latestScan.last_scan_completed_at).toLocaleString("en-IN", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }, [latestScan?.last_scan_completed_at]);

  const indices = market?.indices ?? [];
  const hasMarket = market && (indices.length > 0 || market.vix);

  return (
    <div className="page-container markets-page">
      <header className="page-hero">
        <div>
          <p className="ds-label">Markets</p>
          <h1 className="ds-display">Market overview</h1>
          <p className="ds-muted">
            Indices, watchlist, and scanner highlights — ready for decisions.
            {refreshing ? " · Updating…" : ""}
          </p>
        </div>
        <div className="page-hero__actions">
          <Button variant="secondary" onClick={() => void load(true)} disabled={refreshing}>
            Refresh
          </Button>
          <Button variant="trade" onClick={() => navigate("/scanner")}>
            TRADE
          </Button>
        </div>
      </header>

      {error ? (
        <Card className="error-state">
          <h2 className="ds-title">Could not load markets</h2>
          <p className="ds-muted">{error}</p>
        </Card>
      ) : null}

      <Card>
        <CardHeader
          label="Indices"
          title="Market summary"
          actions={<StatusPill status={hasMarket ? "online" : "idle"} label={hasMarket ? "Quotes" : "Waiting"} />}
        />
        {loading && !market ? (
          <MetricCardSkeleton count={4} />
        ) : !hasMarket ? (
          <EmptyState
            title="Market data unavailable"
            description="Index quotes will appear when the data feed is connected."
            primaryAction={{ label: "Refresh", onClick: () => void load(true), variant: "secondary" }}
          />
        ) : (
          <div className="summary-row workstation-summary markets-indices">
            {indices.map((item: any) => (
              <IndexCard key={item.symbol} item={item} />
            ))}
            {market?.vix ? <IndexCard item={market.vix} /> : null}
          </div>
        )}
        {hasMarket ? (
          <div className="workstation-two-col" style={{ marginTop: 16 }}>
            <MoverList title="Market movers · gainers" rows={market?.top_gainers ?? []} />
            <MoverList title="Market movers · losers" rows={market?.top_losers ?? []} />
          </div>
        ) : null}
      </Card>

      <div className="markets-grid-2">
        <Card>
          <CardHeader
            label="Watchlist"
            title="Your favorites"
            actions={
              <Button variant="ghost" size="sm" onClick={() => navigate("/watchlist")}>
                View all
              </Button>
            }
          />
          {watchlist.length === 0 ? (
            <EmptyState
              title="No watchlist yet"
              description="Star symbols from the scanner or stock page to track them here."
              primaryAction={{ label: "Open Scanner", onClick: () => navigate("/scanner"), variant: "trade" }}
            />
          ) : (
            <ul className="markets-symbol-list">
              {watchlist.slice(0, 8).map((sym) => (
                <li key={sym}>
                  <button type="button" className="markets-symbol-row" onClick={() => navigate(`/scanner?symbol=${sym}`)}>
                    <strong>{sym}</strong>
                    <span className="ds-caption">View</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <CardHeader
            label="Scanner"
            title="Highlights"
            description={lastScanDate ? `Last scan ${lastScanDate}` : "Run a scan to see ideas"}
            actions={
              <Button variant="secondary" size="sm" onClick={() => navigate("/scanner")}>
                Open Scanner
              </Button>
            }
          />
          {loading && !latestScan ? (
            <ListSkeleton items={4} />
          ) : highlights.length === 0 ? (
            <EmptyState
              title="No scanner results"
              description="Run the scanner to surface BUY and WATCH ideas."
              primaryAction={{ label: "Run Scanner", onClick: () => navigate("/scanner"), variant: "trade" }}
            />
          ) : (
            <ul className="markets-symbol-list">
              {highlights.map((c: any) => (
                <li key={c.symbol}>
                  <button
                    type="button"
                    className="markets-symbol-row"
                    onClick={() => navigate(`/scanner?symbol=${encodeURIComponent(c.symbol)}`)}
                  >
                    <span>
                      <strong>{c.symbol}</strong>
                      <span className="ds-caption" style={{ marginLeft: 8 }}>
                        {c.recommendation ?? "—"}
                      </span>
                    </span>
                    <span className="ds-caption">Score {c.score != null ? Number(c.score).toFixed(0) : "—"}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="markets-grid-2">
        <Card>
          <CardHeader label="Quick trade" title="Paper Desk" description="Practice orders with real market context." />
          <div className="markets-quick-trade">
            <Button variant="buy" onClick={() => navigate("/paper?side=BUY")}>
              BUY
            </Button>
            <Button variant="sell" onClick={() => navigate("/paper?side=SELL")}>
              SELL
            </Button>
            <Button variant="secondary" onClick={() => navigate("/paper")}>
              Open Paper Desk
            </Button>
          </div>
        </Card>

        <Card>
          <CardHeader label="Saved scans" title="Presets" />
          {savedScans.length === 0 ? (
            <EmptyState
              title="No saved scans"
              description="Save filter setups from the scanner for one-click reuse."
              primaryAction={{ label: "Open Scanner", onClick: () => navigate("/scanner"), variant: "secondary" }}
            />
          ) : (
            <div className="workstation-list">
              {savedScans.map((scan) => (
                <article key={scan.id} className="scan-history-item">
                  <div>
                    <strong>{scan.name}</strong>
                    <p className="muted-copy">
                      {scan.universe} · {scan.timeframe} · top {scan.top_n}
                    </p>
                  </div>
                  <div className="meta-inline">
                    <button
                      type="button"
                      className="button small-button"
                      onClick={() => {
                        onLoadSavedScan?.(scan);
                        navigate("/scanner");
                      }}
                    >
                      Load
                    </button>
                    <button
                      type="button"
                      className="button ghost-button small-button"
                      onClick={async () => {
                        await deleteScannerPreset(scan.id);
                        await load(true);
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader label="Alerts" title="Price alerts" />
        <div className="workstation-two-col">
          <div className="subpanel">
            <h3 className="ds-title" style={{ fontSize: "0.95rem" }}>
              Create price alert
            </h3>
            <div className="paper-ticket-grid">
              <input
                placeholder="Name"
                value={priceAlert.name}
                onChange={(e) => setPriceAlert({ ...priceAlert, name: e.target.value })}
                aria-label="Alert name"
              />
              <input
                placeholder="Symbol"
                value={priceAlert.symbol}
                onChange={(e) => setPriceAlert({ ...priceAlert, symbol: e.target.value.toUpperCase() })}
                aria-label="Symbol"
              />
              <select
                value={priceAlert.condition}
                onChange={(e) => setPriceAlert({ ...priceAlert, condition: e.target.value })}
                aria-label="Condition"
              >
                <option value=">=">≥</option>
                <option value="<=">≤</option>
              </select>
              <input
                type="number"
                placeholder="Price"
                value={priceAlert.target_price}
                onChange={(e) => setPriceAlert({ ...priceAlert, target_price: e.target.value })}
                aria-label="Target price"
              />
            </div>
            <Button variant="secondary" style={{ marginTop: 10 }} onClick={() => void handleCreatePriceAlert()}>
              Create alert
            </Button>
          </div>
          <div className="workstation-list">
            {alerts.length === 0 ? (
              <p className="ds-muted">No active alerts.</p>
            ) : (
              alerts.map((alert) => (
                <article key={alert.id} className="scan-history-item">
                  <div>
                    <strong>{alert.name}</strong>
                    <p className="muted-copy">
                      {alert.alert_type} {alert.symbol ?? alert.scan_name ?? ""} · {alert.last_message ?? "Waiting"}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="button ghost-button small-button"
                    onClick={async () => {
                      await deleteWorkstationAlert(alert.id);
                      await load(true);
                    }}
                  >
                    Delete
                  </button>
                </article>
              ))
            )}
          </div>
        </div>
      </Card>
    </div>
  );
});

const IndexCard = memo(function IndexCard({ item }: { item: any }) {
  const change = Number(item.change_pct ?? item.change_percent ?? item.pct_change ?? 0);
  return (
    <article className="metric-card markets-index-card">
      <span>{item.name || item.symbol}</span>
      <strong>
        {item.ltp != null
          ? Number(item.ltp).toLocaleString("en-IN", { maximumFractionDigits: 2 })
          : item.price != null
            ? Number(item.price).toLocaleString("en-IN", { maximumFractionDigits: 2 })
            : "—"}
      </strong>
      <PnL value={change} currency={false} percent digits={2} size="sm" />
    </article>
  );
});

const MoverList = memo(function MoverList({ title, rows }: { title: string; rows: any[] }) {
  return (
    <div className="subpanel">
      <h3 className="ds-title" style={{ fontSize: "0.95rem", marginBottom: 8 }}>
        {title}
      </h3>
      {!rows?.length ? (
        <p className="ds-muted">No data</p>
      ) : (
        <ul className="markets-symbol-list">
          {rows.slice(0, 5).map((row: any) => (
            <li key={row.symbol || row.name}>
              <div className="markets-symbol-row" style={{ cursor: "default" }}>
                <strong>{row.symbol || row.name}</strong>
                <PnL
                  value={Number(row.change_pct ?? row.score ?? row.pct_change ?? 0)}
                  currency={false}
                  percent={row.change_pct != null || row.pct_change != null}
                  digits={1}
                  size="sm"
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
});

export default MarketsPage;

// silence unused import if ProfilePreferences only used for typing elsewhere
void (0 as unknown as ProfilePreferences);

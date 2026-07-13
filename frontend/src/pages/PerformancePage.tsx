import { lazy, memo, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchAnalytics, fetchPaperTradingDashboard } from "../api";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import { MetricCardSkeleton, ChartSkeleton, PanelSkeleton } from "../components/Skeleton";
import { Card, CardHeader, EmptyState, Button, PnL, StatCard } from "../design-system";

const DailyAnalyticsPanel = lazy(() =>
  import("../components/DailyAnalyticsPanel").then((m) => ({ default: m.DailyAnalyticsPanel })),
);

function formatEquity(v: number | null | undefined): string {
  if (v == null) return "—";
  return `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function formatWinRate(v: number | null | undefined): string {
  if (v == null) return "—";
  const rate = Number(v) * (Number(v) > 1 ? 1 : 100);
  return `${rate.toFixed(1)}%`;
}

function formatProfitFactor(v: number | null | undefined): string {
  if (v == null) return "—";
  return Number(v).toFixed(2);
}

function formatDrawdown(v: number | null | undefined): string | null {
  if (v == null) return null;
  const abs = -Math.abs(Number(v));
  const isPct = !String(v).includes(".") || Math.abs(Number(v)) < 5;
  const isCurrency = Math.abs(Number(v)) >= 5;
  return String(abs);
}

export function PerformancePage() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<any | null>(() => getCached(CACHE_KEYS.paperDashboard));
  const [analytics, setAnalytics] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadingDash, setLoadingDash] = useState(!getCached(CACHE_KEYS.paperDashboard));
  const [loadingAnalytics, setLoadingAnalytics] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [dash, analyticsData] = await Promise.all([
        fetchPaperTradingDashboard().catch(() => null),
        fetchAnalytics().catch(() => null),
      ]);
      if (cancelled) return;
      if (dash) setDashboard(dash);
      setLoadingDash(false);
      if (analyticsData) setAnalytics(analyticsData);
      setLoadingAnalytics(false);
    })();
    return () => { cancelled = true; };
  }, []);

  const account = dashboard?.account;
  const equity = account?.equity ?? account?.balance ?? null;
  const pnl = account?.unrealized_pnl ?? account?.day_pnl ?? null;
  const realized = account?.realized_pnl ?? null;
  const positions = dashboard?.positions?.length ?? 0;
  const trades = dashboard?.trades?.length ?? 0;

  const goPaper = useCallback(() => navigate("/paper"), [navigate]);
  const goBuy = useCallback(() => navigate("/paper?side=BUY"), [navigate]);
  const goScanner = useCallback(() => navigate("/scanner"), [navigate]);

  const showEmpty = !dashboard && !analytics && !loadingDash && !loadingAnalytics;
  const showContent = dashboard || analytics;

  return (
    <div className="page-container perf-page">
      <header className="perf-hero">
        <div>
          <p className="ds-label">Performance</p>
          <h1 className="ds-display">Portfolio analytics</h1>
          <p className="ds-muted">Track equity, P&amp;L, and trading stats from your paper account.</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button variant="secondary" onClick={goPaper}>
            Paper Desk
          </Button>
          <Button variant="trade" onClick={goBuy}>
            TRADE
          </Button>
        </div>
      </header>

      {error ? (
        <Card className="error-state">
          <h2 className="ds-title">Could not load performance</h2>
          <p className="ds-muted">{error}</p>
        </Card>
      ) : null}

      {showEmpty ? (
        <Card>
          <EmptyState
            title="No performance data yet"
            description="Place paper trades to build equity history and analytics."
            primaryAction={{ label: "Buy stock", onClick: goBuy, variant: "buy" }}
            secondaryAction={{ label: "Open Scanner", onClick: goScanner, variant: "ghost" }}
          />
        </Card>
      ) : null}

      {showContent ? (
        <>
          <SummaryRow
            equity={equity}
            pnl={pnl}
            realized={realized}
            positions={positions}
            trades={trades}
            loading={loadingDash}
          />

          {loadingAnalytics && !analytics ? (
            <Card>
              <CardHeader label="Stats" title="Trading summary" />
              <MetricCardSkeleton count={4} />
            </Card>
          ) : null}

          {analytics ? (
            <AnalyticsSection analytics={analytics} />
          ) : null}

          <Card>
            <CardHeader label="Daily" title="Day-by-day analytics" />
            <Suspense fallback={<ChartSkeleton height={200} />}>
              <DailyAnalyticsPanel />
            </Suspense>
          </Card>
        </>
      ) : null}
    </div>
  );
}

const SummaryRow = memo(function SummaryRow({
  equity,
  pnl,
  realized,
  positions,
  trades,
  loading,
}: {
  equity: number | null;
  pnl: number | null;
  realized: number | null;
  positions: number;
  trades: number;
  loading: boolean;
}) {
  if (loading && equity == null) {
    return (
      <div className="perf-summary">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="app-skel" style={{ height: 88, borderRadius: 14 }} />
        ))}
      </div>
    );
  }
  return (
    <div className="perf-summary">
      <StatCard label="Equity" value={formatEquity(equity)} />
      <StatCard label="Unrealized P&L" value={<PnL value={pnl} showBadge />} />
      <StatCard label="Realized P&L" value={<PnL value={realized} />} />
      <StatCard label="Open positions" value={positions} />
      <StatCard label="Closed trades" value={trades} />
    </div>
  );
});

const AnalyticsSection = memo(function AnalyticsSection({ analytics }: { analytics: any }) {
  const hasWinRate = analytics.win_rate != null;
  const hasTotalTrades = analytics.total_trades != null;
  const hasProfitFactor = analytics.profit_factor != null;
  const hasDrawdown = analytics.max_drawdown != null;

  if (!hasWinRate && !hasTotalTrades && !hasProfitFactor && !hasDrawdown) return null;

  return (
    <Card>
      <CardHeader label="Stats" title="Trading summary" />
      <div className="perf-analytics">
        {hasWinRate ? (
          <StatCard label="Win rate" value={formatWinRate(analytics.win_rate)} tone={Number(analytics.win_rate) >= 0.5 ? "positive" : "negative"} />
        ) : null}
        {hasTotalTrades ? (
          <StatCard label="Total trades" value={analytics.total_trades} />
        ) : null}
        {hasProfitFactor ? (
          <StatCard label="Profit factor" value={formatProfitFactor(analytics.profit_factor)} tone={Number(analytics.profit_factor) >= 1 ? "positive" : "warning"} />
        ) : null}
        {hasDrawdown ? (
          <StatCard label="Max drawdown" value={<PnL value={-Math.abs(Number(analytics.max_drawdown))} />} tone="negative" />
        ) : null}
      </div>
    </Card>
  );
});

export default PerformancePage;

/**
 * Paper Trading Analytics Dashboard — metrics, charts, time filters.
 * Uses recharts (bundled) so Chart.js CDN failures never block the tab.
 */
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { fetchAnalytics } from "../api";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import { MetricCardSkeleton, ChartSkeleton, TableSkeleton } from "./Skeleton";

export type AnalyticsPeriod =
  | "today"
  | "week"
  | "month"
  | "last_month"
  | "last_3_months"
  | "last_6_months"
  | "last_year"
  | "all";

const PERIODS: [AnalyticsPeriod, string][] = [
  ["today", "Today"],
  ["week", "This Week"],
  ["month", "This Month"],
  ["last_month", "Last Month"],
  ["last_3_months", "Last 3 Months"],
  ["last_6_months", "Last 6 Months"],
  ["last_year", "Last Year"],
  ["all", "All Time"],
];

const PIE_COLORS = ["#2ecc71", "#e74c3c", "#3b82f6", "#f59e0b", "#a855f7", "#06b6d4", "#64748b", "#10b981"];

function money(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const sign = v < 0 ? "-" : "";
  return `${sign}₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${Number(n).toFixed(2)}%`;
}

function Metric({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "pos" | "neg" | "neutral";
}) {
  const cls =
    tone === "pos" ? "metric-card metric-card-positive" : tone === "neg" ? "metric-card metric-card-negative" : "metric-card";
  return (
    <div className={cls}>
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <p>{hint}</p> : null}
    </div>
  );
}

function ChartCard({ title, children, height = 240 }: { title: string; children: React.ReactNode; height?: number }) {
  return (
    <div className="panel" style={{ flex: "1 1 340px", minWidth: 280, padding: 12 }}>
      <div className="panel-header" style={{ marginBottom: 8 }}>
        <div>
          <p className="section-label">Chart</p>
          <h2 style={{ fontSize: "1rem", margin: 0 }}>{title}</h2>
        </div>
      </div>
      <div style={{ width: "100%", height }}>{children}</div>
    </div>
  );
}

const tooltipStyle = {
  background: "var(--surface, #1e2430)",
  border: "1px solid var(--border, #333)",
  borderRadius: 10,
  fontSize: 12,
};

export function AnalyticsPanel() {
  const [period, setPeriod] = useState<AnalyticsPeriod>("all");
  const cacheKey = `${CACHE_KEYS.paperAnalytics}:${period}`;
  const [data, setData] = useState<any | null>(() => getCached(cacheKey));
  const [loading, setLoading] = useState(() => !getCached(cacheKey));
  const [err, setErr] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  const load = useCallback(
    async (force = false) => {
      if (!data) setLoading(true);
      setErr(null);
      try {
        const resp = await fetchAnalytics({ period, force });
        setData(resp);
      } catch (e: any) {
        // Only surface error when we have nothing to show
        if (!data) setErr(e?.message ?? String(e));
      } finally {
        setLoading(false);
      }
    },
    [period, data],
  );

  useEffect(() => {
    setData(getCached(`${CACHE_KEYS.paperAnalytics}:${period}`));
    void load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, retryKey]);

  const winLossData = useMemo(
    () => [
      { name: "Wins", value: data?.wins ?? data?.winning_trades ?? 0 },
      { name: "Losses", value: data?.losses ?? data?.losing_trades ?? 0 },
    ],
    [data],
  );

  const sectorData = useMemo(
    () =>
      (data?.sector_performance || []).map((s: any) => ({
        name: s.sector,
        value: Math.abs(Number(s.pnl) || 0),
        pnl: Number(s.pnl) || 0,
      })),
    [data],
  );

  const allocationData = useMemo(
    () =>
      (data?.portfolio_allocation || []).map((a: any) => ({
        name: a.symbol,
        value: Number(a.value) || 0,
      })),
    [data],
  );

  if (loading && !data) {
    return (
      <section aria-busy="true" data-testid="analytics-panel-loading">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          {PERIODS.map(([k, label]) => (
            <button key={k} type="button" className="button ghost-button" disabled>
              {label}
            </button>
          ))}
        </div>
        <MetricCardSkeleton count={12} />
        <div style={{ display: "flex", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
          <ChartSkeleton height={220} />
          <ChartSkeleton height={220} />
          <ChartSkeleton height={220} />
        </div>
        <div style={{ marginTop: 12 }}>
          <TableSkeleton rows={4} cols={4} />
        </div>
      </section>
    );
  }

  if (err && !data) {
    return (
      <div className="empty-state" data-testid="analytics-panel-error">
        <h2>Failed to load analytics</h2>
        <p>{err}</p>
        <button type="button" className="button primary-button" onClick={() => setRetryKey((k) => k + 1)}>
          Retry
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="empty-state">
        <h2>No analytics yet</h2>
        <p>Close a few paper trades to populate this dashboard.</p>
      </div>
    );
  }

  const totalPnl = Number(data.total_pnl ?? 0);
  const todaysPnl = Number(data.todays_pnl ?? 0);
  const realized = Number(data.realized_pnl ?? 0);
  const unrealized = Number(data.unrealized_pnl ?? 0);

  return (
    <section className="analytics-dashboard" data-testid="analytics-panel">
      <div
        style={{
          display: "flex",
          gap: 8,
          flexWrap: "wrap",
          marginBottom: 16,
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {PERIODS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              className={period === k ? "button primary-button" : "button ghost-button"}
              onClick={() => setPeriod(k)}
              style={{ fontSize: "0.85rem", padding: "0.4rem 0.7rem" }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="muted-copy" style={{ fontSize: "0.85rem" }}>
          {data.range_label || period}
          {loading ? " · refreshing…" : ""}
        </div>
      </div>

      {/* Overview cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <Metric label="Total Trades" value={data.total_trades ?? 0} hint="Closed trades" />
        <Metric label="Winning Trades" value={data.winning_trades ?? data.wins ?? 0} tone="pos" />
        <Metric label="Losing Trades" value={data.losing_trades ?? data.losses ?? 0} tone="neg" />
        <Metric label="Win Rate" value={pct(data.win_rate_pct)} />
        <Metric label="Total P&L" value={money(totalPnl)} tone={totalPnl >= 0 ? "pos" : "neg"} />
        <Metric label="Today's P&L" value={money(todaysPnl)} tone={todaysPnl >= 0 ? "pos" : "neg"} />
        <Metric label="Unrealized P&L" value={money(unrealized)} tone={unrealized >= 0 ? "pos" : "neg"} />
        <Metric label="Realized P&L" value={money(realized)} tone={realized >= 0 ? "pos" : "neg"} />
        <Metric label="Portfolio Value" value={money(data.portfolio_value)} />
        <Metric label="Available Cash" value={money(data.available_cash)} />
        <Metric label="Capital Utilized" value={money(data.capital_utilized)} />
        <Metric label="ROI %" value={pct(data.roi_pct)} tone={Number(data.roi_pct) >= 0 ? "pos" : "neg"} />
        <Metric label="Average Profit" value={money(data.average_profit)} tone="pos" />
        <Metric label="Average Loss" value={money(data.average_loss)} tone="neg" />
        <Metric label="Profit Factor" value={data.profit_factor ?? "—"} />
        <Metric label="Avg Risk:Reward" value={data.average_risk_reward ?? "—"} />
        <Metric label="Largest Profit" value={money(data.largest_profit ?? data.best_trade_amount)} tone="pos" />
        <Metric label="Largest Loss" value={money(data.largest_loss ?? data.worst_trade_amount)} tone="neg" />
        <Metric label="Max Drawdown" value={money(data.max_drawdown)} hint={pct(data.max_drawdown_pct)} tone="neg" />
        <Metric label="Sharpe Ratio" value={data.sharpe_ratio ?? "—"} hint="Optional" />
        <Metric label="Open Positions" value={data.open_positions_count ?? 0} />
        <Metric
          label="Current Streak"
          value={`${data.current_streak_type ?? "none"} ${data.current_streak_count ?? 0}`}
        />
      </div>

      {/* Charts */}
      <div style={{ display: "flex", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <ChartCard title="Equity Curve">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.equity_curve?.length ? data.equity_curve : data.cumulative_pnl || []}>
              <defs>
                <linearGradient id="eqFillA" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2b6cff" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#2b6cff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" opacity={0.4} />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area
                type="monotone"
                dataKey={data.equity_curve?.length ? "equity" : "pnl"}
                stroke="#2b6cff"
                fill="url(#eqFillA)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Daily P&L">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.daily_pnl || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" opacity={0.4} />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="pnl" fill="#2b6cff">
                {(data.daily_pnl || []).map((e: any, i: number) => (
                  <Cell key={i} fill={Number(e.pnl) >= 0 ? "#1b7a1b" : "#a60b0b"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Monthly P&L">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.monthly_pnl || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" opacity={0.4} />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="pnl">
                {(data.monthly_pnl || []).map((e: any, i: number) => (
                  <Cell key={i} fill={Number(e.pnl) >= 0 ? "#1b7a1b" : "#a60b0b"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Win / Loss Distribution" height={240}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={winLossData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={78} paddingAngle={3}>
                {winLossData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Sector-wise Performance">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sectorData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" opacity={0.4} />
              <XAxis dataKey="name" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="pnl">
                {sectorData.map((e: any, i: number) => (
                  <Cell key={i} fill={Number(e.pnl) >= 0 ? "#1b7a1b" : "#a60b0b"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Trade Frequency">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.trade_frequency || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" opacity={0.4} />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis allowDecimals={false} tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" fill="#a855f7" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Capital Growth">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.capital_growth?.length ? data.capital_growth : data.equity_curve || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" opacity={0.4} />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Line
                type="monotone"
                dataKey={data.capital_growth?.length ? "value" : "equity"}
                stroke="#06b6d4"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Portfolio Allocation" height={240}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={allocationData.length ? allocationData : [{ name: "Cash", value: 1 }]}
                dataKey="value"
                nameKey="name"
                outerRadius={78}
              >
                {(allocationData.length ? allocationData : [{ name: "Cash", value: 1 }]).map((_: { name: string; value: number }, i: number) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => money(v)} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Cumulative Returns">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.cumulative_pnl || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border, #333)" opacity={0.4} />
              <XAxis dataKey="date" tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <YAxis tick={{ fill: "var(--text-muted)", fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="pnl" stroke="#10b981" fill="#10b98133" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Trade analytics */}
      <section className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-header">
          <div>
            <p className="section-label">Trade Analytics</p>
            <h2>Trade stats</h2>
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Metric label="Avg Holding Time" value={`${Number(data.average_holding_minutes ?? 0).toFixed(1)} min`} />
          <Metric label="Avg Entry Price" value={money(data.average_entry_price)} />
          <Metric label="Avg Exit Price" value={money(data.average_exit_price)} />
          <Metric
            label="Best Trade"
            value={`${data.best_trade_symbol ?? "—"} ${data.best_trade_amount != null ? money(data.best_trade_amount) : ""}`}
            tone="pos"
          />
          <Metric
            label="Worst Trade"
            value={`${data.worst_trade_symbol ?? "—"} ${data.worst_trade_amount != null ? money(data.worst_trade_amount) : ""}`}
            tone="neg"
          />
          <Metric label="Most Profitable Symbol" value={data.most_profitable_symbol ?? "—"} tone="pos" />
          <Metric label="Most Losing Symbol" value={data.most_losing_symbol ?? "—"} tone="neg" />
          <Metric label="Longest Win Streak" value={data.longest_winning_streak ?? 0} />
          <Metric label="Longest Loss Streak" value={data.longest_losing_streak ?? 0} />
          <Metric label="Avg Return %" value={pct(data.average_return_pct)} />
          <Metric
            label="Avg Holding Period"
            value={`${Number(data.average_holding_period ?? data.average_holding_minutes ?? 0).toFixed(1)} min`}
          />
        </div>
      </section>

      {/* Performance metrics */}
      <section className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-header">
          <div>
            <p className="section-label">Performance Metrics</p>
            <h2>Orders</h2>
          </div>
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Metric label="Total Orders" value={data.total_orders ?? 0} />
          <Metric label="Executed Orders" value={data.executed_orders ?? 0} />
          <Metric label="Cancelled Orders" value={data.cancelled_orders ?? 0} />
          <Metric label="Pending Orders" value={data.pending_orders ?? 0} />
          <Metric label="Buy Orders" value={data.buy_orders ?? 0} />
          <Metric label="Sell Orders" value={data.sell_orders ?? 0} />
          <Metric label="Intraday Trades" value={data.intraday_trades ?? 0} />
          <Metric label="Delivery Trades" value={data.delivery_trades ?? 0} />
        </div>
      </section>

      {/* Holding periods table */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Holding periods</p>
            <h2>Per-symbol stats</h2>
          </div>
        </div>
        <div className="table-scroll">
          <table className="candidate-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Avg hold (min)</th>
                <th>Total trades</th>
                <th>Win rate</th>
                <th>Total P&L</th>
              </tr>
            </thead>
            <tbody>
              {(data.holding_periods || []).length === 0 ? (
                <tr>
                  <td colSpan={5} className="muted-copy">
                    No closed trades in this period.
                  </td>
                </tr>
              ) : (
                (data.holding_periods || []).map((row: any) => (
                  <tr key={row.symbol}>
                    <td>{row.symbol}</td>
                    <td className="number-cell">{Number(row.avg_holding_minutes ?? 0).toFixed(1)}</td>
                    <td>{row.total_trades}</td>
                    <td>{row.win_rate_pct}%</td>
                    <td className="number-cell">{money(row.total_pnl)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

export default memo(AnalyticsPanel);

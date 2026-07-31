import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchDailyAnalytics,
  saveDailyJournal,
  type DailyAnalyticsPeriod,
} from "../api";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import { MetricCardSkeleton, ChartSkeleton, TableSkeleton } from "./Skeleton";
import { StatCard } from "../design-system";
import { FeatureGuard } from "./FeatureGuard";

declare const Chart: any;

type Props = {
  onRefresh?: () => void;
};

function money(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `${Number(n).toFixed(2)}%`;
}

function scoreClass(score: number): string {
  if (score >= 90) return "score-excellent";
  if (score >= 75) return "score-good";
  if (score >= 55) return "score-avg";
  return "score-poor";
}

export function DailyAnalyticsPanel({ onRefresh }: Props) {
  const [period, setPeriod] = useState<DailyAnalyticsPeriod>("today");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const cacheKey = CACHE_KEYS.paperDailyAnalytics(`${period}:${customStart}:${customEnd}`);
  const [data, setData] = useState<any | null>(() => getCached(cacheKey));
  const [loading, setLoading] = useState(() => !getCached(cacheKey));
  const [error, setError] = useState<string | null>(null);

  const [journal, setJournal] = useState({
    observations: "",
    mistakes: "",
    lessons: "",
    tomorrow_plan: "",
  });
  const [journalSaving, setJournalSaving] = useState(false);
  const [journalMsg, setJournalMsg] = useState<string | null>(null);
  const saveTimer = useRef<number | null>(null);

  const equityRef = useRef<HTMLCanvasElement | null>(null);
  const hourlyRef = useRef<HTMLCanvasElement | null>(null);
  const pieRef = useRef<HTMLCanvasElement | null>(null);
  const sectorRef = useRef<HTMLCanvasElement | null>(null);
  const capitalRef = useRef<HTMLCanvasElement | null>(null);
  const chartsRef = useRef<Record<string, any>>({});

  const load = useCallback(
    async (force = false) => {
      if (!data) setLoading(true);
      setError(null);
      try {
        const resp = await fetchDailyAnalytics({
          period,
          start_date: period === "custom" ? customStart : undefined,
          end_date: period === "custom" ? customEnd : undefined,
          include_ai: true,
          force,
        });
        setData(resp);
        const j = resp?.journal;
        if (j) {
          setJournal({
            observations: j.observations || "",
            mistakes: j.mistakes || "",
            lessons: j.lessons || "",
            tomorrow_plan: j.tomorrow_plan || "",
          });
        }
      } catch (e: any) {
        if (!data) setError(e?.message || "Failed to load daily analytics");
      } finally {
        setLoading(false);
      }
    },
    [period, customStart, customEnd, data],
  );

  useEffect(() => {
    void load(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, customStart, customEnd]);

  useEffect(() => {
    if (!data?.charts || typeof Chart === "undefined") return;
    Object.values(chartsRef.current).forEach((c) => c?.destroy?.());
    chartsRef.current = {};

    try {
      const eq = data.charts.equity_curve || [];
      if (equityRef.current && eq.length) {
        chartsRef.current.equity = new Chart(equityRef.current.getContext("2d"), {
          type: "line",
          data: {
            labels: eq.map((p: any) => (p.t ? new Date(p.t).toLocaleTimeString() : "")),
            datasets: [
              {
                label: "Equity",
                data: eq.map((p: any) => p.equity),
                borderColor: "#2b6cff",
                fill: false,
                tension: 0.2,
              },
            ],
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
        });
      }

      const hourly = data.charts.hourly_pnl || [];
      if (hourlyRef.current) {
        chartsRef.current.hourly = new Chart(hourlyRef.current.getContext("2d"), {
          type: "bar",
          data: {
            labels: hourly.map((h: any) => h.slot),
            datasets: [
              {
                label: "P&L",
                data: hourly.map((h: any) => h.pnl),
                backgroundColor: hourly.map((h: any) => (h.pnl >= 0 ? "#1b7a1b" : "#a60b0b")),
              },
            ],
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
        });
      }

      const wl = data.charts.win_loss_ratio || data.charts.trade_distribution || {};
      if (pieRef.current) {
        chartsRef.current.pie = new Chart(pieRef.current.getContext("2d"), {
          type: "doughnut",
          data: {
            labels: ["Wins", "Losses"],
            datasets: [
              {
                data: [wl.wins || 0, wl.losses || 0],
                backgroundColor: ["#2ecc71", "#e74c3c"],
              },
            ],
          },
          options: { responsive: true, maintainAspectRatio: false },
        });
      }

      const sectors = data.charts.sector_allocation || [];
      if (sectorRef.current && sectors.length) {
        chartsRef.current.sector = new Chart(sectorRef.current.getContext("2d"), {
          type: "pie",
          data: {
            labels: sectors.map((s: any) => s.name),
            datasets: [
              {
                data: sectors.map((s: any) => s.value),
                backgroundColor: ["#3b82f6", "#06b6d4", "#a855f7", "#f59e0b", "#10b981", "#64748b", "#ef4444"],
              },
            ],
          },
          options: { responsive: true, maintainAspectRatio: false },
        });
      }

      const cap = data.charts.capital_usage || {};
      if (capitalRef.current) {
        chartsRef.current.capital = new Chart(capitalRef.current.getContext("2d"), {
          type: "doughnut",
          data: {
            labels: ["Cash", "Invested"],
            datasets: [
              {
                data: [cap.cash || 0, cap.invested || 0],
                backgroundColor: ["#64748b", "#3b82f6"],
              },
            ],
          },
          options: { responsive: true, maintainAspectRatio: false },
        });
      }
    } catch (e) {
      console.warn("Daily analytics chart render failed", e);
    }

    return () => {
      Object.values(chartsRef.current).forEach((c) => c?.destroy?.());
      chartsRef.current = {};
    };
  }, [data]);

  const scheduleJournalSave = useCallback(
    (next: typeof journal) => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(async () => {
        setJournalSaving(true);
        try {
          await saveDailyJournal({
            journal_date: data?.journal?.journal_date,
            ...next,
          });
          setJournalMsg("Journal saved");
          window.setTimeout(() => setJournalMsg(null), 2000);
        } catch {
          setJournalMsg("Save failed");
        } finally {
          setJournalSaving(false);
        }
      }, 800);
    },
    [data?.journal?.journal_date],
  );

  function updateJournal(field: keyof typeof journal, value: string) {
    const next = { ...journal, [field]: value };
    setJournal(next);
    scheduleJournalSave(next);
  }

  function exportCsv() {
    if (!data) return;
    const rows = data.symbol_performance || [];
    const header = ["Symbol", "Entry", "Exit", "Current", "Qty", "Return%", "HoldMin", "PnL", "Status"];
    const lines = [header.join(",")];
    for (const r of rows) {
      lines.push(
        [
          r.symbol,
          r.entry,
          r.exit ?? "",
          r.current_price,
          r.quantity,
          r.return_pct,
          r.holding_time_minutes,
          r.pnl,
          r.status,
        ].join(","),
      );
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `daily-analytics-${data.range_label || "export"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportCsvAlt() { exportCsv(); }
  function exportPdf() { window.print(); }

  const ov = data?.overview;
  const score = data?.trading_score;
  const perf = data?.performance;
  const port = data?.portfolio;
  const summary = data?.trade_summary;
  const risk = data?.risk_analysis;
  const emotional = data?.emotional_analysis;
  const ai = data?.ai_insights;

  const metricTiles = useMemo(() => {
    if (!ov) return [];
    return [
      ["Today's Profit", money(ov.todays_profit)],
      ["Today's Loss", money(ov.todays_loss)],
      ["Return %", pct(ov.todays_return_pct)],
      ["Realized P&L", money(ov.todays_realized_pnl)],
      ["Unrealized P&L", money(ov.todays_unrealized_pnl)],
      ["Trades", ov.trades_executed],
      ["Wins", ov.winning_trades],
      ["Losses", ov.losing_trades],
      ["Open", ov.open_positions],
      ["Closed", ov.closed_positions],
      ["Capital Used", money(ov.capital_used)],
      ["Cash", money(ov.cash_remaining)],
      ["Largest Win", money(ov.largest_winner)],
      ["Largest Loss", money(ov.largest_loser)],
      ["Avg Win", money(ov.average_win)],
      ["Avg Loss", money(ov.average_loss)],
    ];
  }, [ov]);

  const periods: [DailyAnalyticsPeriod, string][] = [
    ["today", "Today"],
    ["yesterday", "Yesterday"],
    ["week", "This Week"],
    ["month", "This Month"],
    ["custom", "Custom"],
  ];

  return (
    <section className="da-panel" data-testid="daily-analytics-panel">
      <div className="da-section">
        <div className="da-header">
          <div>
            <p className="da-section__label">Daily Analytics</p>
            <h2 className="da-section__title">Session performance journal</h2>
            <p className="ds-muted" style={{ marginTop: 4 }}>
              {data?.range_label ? `Range: ${data.range_label}` : "Loading range..."} &middot; User-isolated paper book
            </p>
          </div>
          <div className="da-period-bar">
            {periods.map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`button ghost-button ${period === id ? "primary-button" : ""}`}
                onClick={() => setPeriod(id)}
              >
                {label}
              </button>
            ))}
            {period === "custom" ? (
              <>
                <input type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
                <input type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
              </>
            ) : null}
            <button type="button" className="button ghost-button" onClick={() => void load(true)}>Refresh</button>
            <FeatureGuard feature="export_data" loadingFallback={null}>
              <button type="button" className="button ghost-button" onClick={exportCsv} disabled={!data}>CSV</button>
              <button type="button" className="button ghost-button" onClick={exportCsvAlt} disabled={!data}>Excel</button>
              <button type="button" className="button ghost-button" onClick={exportPdf} disabled={!data}>PDF</button>
            </FeatureGuard>
          </div>
        </div>
      </div>

      {error && !data ? (
        <div className="da-section error-state">
          <h2>Failed to load Daily Analytics</h2>
          <p>{error}</p>
          <button type="button" className="button primary-button" onClick={() => void load(true)}>Retry</button>
        </div>
      ) : null}

      <div className="da-overview">
        <div className={`da-score ${score ? scoreClass(score.score) : ""}`} data-testid="daily-trading-score">
          <span className="da-score__label">Daily Trading Score</span>
          {loading && !score ? (
            <div className="app-skel" style={{ height: 48, width: 60, margin: "8px auto", borderRadius: 8 }} />
          ) : (
            <>
              <span className="da-score__value">{score?.score ?? "—"}</span>
              <span className="da-score__desc">{score?.label ?? "—"}</span>
            </>
          )}
        </div>
        <div>
          {loading && !ov ? (
            <MetricCardSkeleton count={8} />
          ) : (
            <div className="da-metrics">
              {metricTiles.map(([label, value]) => (
                <div key={String(label)} className="da-metric">
                  <span className="da-metric__label">{label}</span>
                  <span className="da-metric__value">{value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="da-grid-3">
        <div className="da-section">
          <div className="da-section__header">
            <p className="da-section__label">Trade summary</p>
            <h2 className="da-section__title">Activity</h2>
          </div>
          {loading && !summary ? (
            <MetricCardSkeleton count={4} />
          ) : (
            <div className="da-subgrid-2">
              <div className="da-metric"><span className="da-metric__label">Total trades</span><span className="da-metric__value">{summary?.total_trades ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Executed</span><span className="da-metric__value">{summary?.executed_orders ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Pending</span><span className="da-metric__value">{summary?.pending_orders ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Cancelled</span><span className="da-metric__value">{summary?.cancelled_orders ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Rejected</span><span className="da-metric__value">{summary?.rejected_orders ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Avg hold (min)</span><span className="da-metric__value">{summary?.average_holding_minutes ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Avg size</span><span className="da-metric__value">{money(summary?.average_position_size)}</span></div>
            </div>
          )}
        </div>

        <div className="da-section">
          <div className="da-section__header">
            <p className="da-section__label">Performance</p>
            <h2 className="da-section__title">Edge metrics</h2>
          </div>
          {loading && !perf ? (
            <MetricCardSkeleton count={6} />
          ) : (
            <div className="da-subgrid-2">
              <div className="da-metric"><span className="da-metric__label">Net profit</span><span className="da-metric__value">{money(perf?.net_profit)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Gross profit</span><span className="da-metric__value">{money(perf?.gross_profit)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Gross loss</span><span className="da-metric__value">{money(perf?.gross_loss)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Profit factor</span><span className="da-metric__value">{perf?.profit_factor ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Win rate</span><span className="da-metric__value">{pct(perf?.win_rate)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Loss rate</span><span className="da-metric__value">{pct(perf?.loss_rate)}</span></div>
              <div className="da-metric"><span className="da-metric__label">R:R</span><span className="da-metric__value">{perf?.risk_reward_ratio ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Expectancy</span><span className="da-metric__value">{money(perf?.expectancy)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Max DD</span><span className="da-metric__value">{money(perf?.maximum_drawdown)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Sharpe</span><span className="da-metric__value">{perf?.sharpe_ratio ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Sortino</span><span className="da-metric__value">{perf?.sortino_ratio ?? "—"}</span></div>
              <div className="da-metric"><span className="da-metric__label">Recovery</span><span className="da-metric__value">{perf?.recovery_factor ?? "—"}</span></div>
            </div>
          )}
        </div>

        <div className="da-section">
          <div className="da-section__header">
            <p className="da-section__label">Portfolio</p>
            <h2 className="da-section__title">Allocation</h2>
          </div>
          {loading && !port ? (
            <MetricCardSkeleton count={4} />
          ) : (
            <div className="da-subgrid-2">
              <div className="da-metric"><span className="da-metric__label">Portfolio value</span><span className="da-metric__value">{money(port?.portfolio_value)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Cash</span><span className="da-metric__value">{money(port?.cash_balance)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Invested</span><span className="da-metric__value">{money(port?.invested_amount)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Allocation %</span><span className="da-metric__value">{pct(port?.allocation_pct)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Utilization %</span><span className="da-metric__value">{pct(port?.utilization_pct)}</span></div>
            </div>
          )}
        </div>
      </div>

      <div className="da-section">
        <div className="da-section__header">
          <p className="da-section__label">Charts</p>
          <h2 className="da-section__title">Visual analysis</h2>
        </div>
        {loading && !data ? (
          <div className="da-charts">
            <ChartSkeleton height={200} />
            <ChartSkeleton height={200} />
          </div>
        ) : (
          <div className="da-charts">
            <div className="da-chart">
              <p className="da-section__label" style={{ marginBottom: 8 }}>Daily equity curve</p>
              <canvas ref={equityRef} />
            </div>
            <div className="da-chart">
              <p className="da-section__label" style={{ marginBottom: 8 }}>Hourly P&L</p>
              <canvas ref={hourlyRef} />
            </div>
            <div className="da-chart da-chart--narrow">
              <p className="da-section__label" style={{ marginBottom: 8 }}>Win / Loss</p>
              <canvas ref={pieRef} />
            </div>
            <div className="da-chart da-chart--narrow">
              <p className="da-section__label" style={{ marginBottom: 8 }}>Sector allocation</p>
              <canvas ref={sectorRef} />
            </div>
            <div className="da-chart da-chart--narrow">
              <p className="da-section__label" style={{ marginBottom: 8 }}>Capital usage</p>
              <canvas ref={capitalRef} />
            </div>
          </div>
        )}
      </div>

      <div className="da-grid-4">
        <div className="da-section">
          <p className="da-section__label">Best trade</p>
          <h2 className="da-section__title">{data?.best_trade?.symbol ?? "—"}</h2>
          {data?.best_trade ? (
            <div className="ds-muted">
              <div>Entry {money(data.best_trade.entry)} &rarr; Exit {money(data.best_trade.exit)}</div>
              <div>Profit {money(data.best_trade.profit)} ({pct(data.best_trade.return_pct)})</div>
              <div>Hold {data.best_trade.holding_time_minutes} min</div>
              <div>Reason: {data.best_trade.reason}</div>
            </div>
          ) : (
            <p className="ds-muted">No closed trades in range.</p>
          )}
        </div>
        <div className="da-section">
          <p className="da-section__label">Worst trade</p>
          <h2 className="da-section__title">{data?.worst_trade?.symbol ?? "—"}</h2>
          {data?.worst_trade ? (
            <div className="ds-muted">
              <div>Loss {money(data.worst_trade.loss)}</div>
              <div>Hold {data.worst_trade.holding_time_minutes} min</div>
              <div>Mistake: {data.worst_trade.mistake}</div>
            </div>
          ) : (
            <p className="ds-muted">No closed trades in range.</p>
          )}
        </div>
        <div className="da-section">
          <p className="da-section__label">Risk analysis</p>
          <h2 className="da-section__title">Exposure</h2>
          {risk ? (
            <div className="da-subgrid-2">
              <div className="da-metric"><span className="da-metric__label">Largest</span><span className="da-metric__value">{money(risk.largest_position)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Smallest</span><span className="da-metric__value">{money(risk.smallest_position)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Risk %</span><span className="da-metric__value">{pct(risk.risk_pct)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Exposure</span><span className="da-metric__value">{money(risk.exposure)}</span></div>
              <div className="da-metric"><span className="da-metric__label">Concentration</span><span className="da-metric__value">{pct(risk.capital_concentration)}</span></div>
            </div>
          ) : (
            <MetricCardSkeleton count={3} />
          )}
        </div>
        <div className="da-section">
          <p className="da-section__label">Emotional analysis</p>
          <h2 className="da-section__title">Process scores</h2>
          {emotional ? (
            <div className="da-subgrid-2">
              <div className="da-metric"><span className="da-metric__label">Discipline</span><span className="da-metric__value">{emotional.discipline}</span></div>
              <div className="da-metric"><span className="da-metric__label">Patience</span><span className="da-metric__value">{emotional.patience}</span></div>
              <div className="da-metric"><span className="da-metric__label">Risk control</span><span className="da-metric__value">{emotional.risk_control}</span></div>
              <div className="da-metric"><span className="da-metric__label">Execution</span><span className="da-metric__value">{emotional.execution_quality}</span></div>
              <div className="da-metric"><span className="da-metric__label">Consistency</span><span className="da-metric__value">{emotional.consistency}</span></div>
            </div>
          ) : (
            <MetricCardSkeleton count={3} />
          )}
        </div>
      </div>

      <div className="da-section">
        <div className="da-section__header">
          <p className="da-section__label">Time analysis</p>
          <h2 className="da-section__title">Trades by session slot</h2>
        </div>
        {loading && !data ? (
          <TableSkeleton rows={3} cols={3} />
        ) : (
          <div className="da-table-scroll">
            <table className="perf-table">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Trades</th>
                  <th>P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {(data?.time_analysis || []).map((row: any) => (
                  <tr key={row.slot}>
                    <td>{row.slot}</td>
                    <td>{row.trades}</td>
                    <td className="number-cell">{money(row.pnl)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="da-grid-2">
        <div className="da-section">
          <div className="da-section__header">
            <p className="da-section__label">Sector analysis</p>
            <h2 className="da-section__title">Allocation &amp; P&amp;L</h2>
          </div>
          {loading && !data ? (
            <TableSkeleton rows={4} cols={5} />
          ) : (
            <div className="da-table-scroll">
              <table className="perf-table">
                <thead>
                  <tr>
                    <th>Sector</th>
                    <th>Trades</th>
                    <th className="perf-hide-mobile">Allocation</th>
                    <th>Profit</th>
                    <th>Loss</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.sector_analysis || []).map((s: any) => (
                    <tr key={s.sector}>
                      <td>{s.sector}</td>
                      <td>{s.trades}</td>
                      <td className="number-cell perf-hide-mobile">{money(s.allocation)}</td>
                      <td className="number-cell">{money(s.profit)}</td>
                      <td className="number-cell">{money(s.loss)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="da-section">
          <div className="da-section__header">
            <p className="da-section__label">Symbol performance</p>
            <h2 className="da-section__title">Per-name results</h2>
          </div>
          {loading && !data ? (
            <TableSkeleton rows={5} cols={6} />
          ) : (
            <div className="da-table-scroll">
              <table className="perf-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Entry</th>
                    <th className="perf-hide-mobile">Exit</th>
                    <th className="perf-hide-tablet">Qty</th>
                    <th>Return %</th>
                    <th className="perf-hide-mobile">Hold</th>
                    <th>P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.symbol_performance || []).map((r: any, i: number) => (
                    <tr key={`${r.symbol}-${i}`}>
                      <td>{r.symbol}</td>
                      <td className="number-cell">{money(r.entry)}</td>
                      <td className="number-cell perf-hide-mobile">{r.exit != null ? money(r.exit) : "—"}</td>
                      <td className="perf-hide-tablet">{r.quantity}</td>
                      <td className="number-cell">{pct(r.return_pct)}</td>
                      <td className="perf-hide-mobile">{r.holding_time_minutes}m</td>
                      <td className="number-cell">{money(r.pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="da-grid-3">
        <div className="da-section">
          <div className="da-section__header">
            <p className="da-section__label">AI insights</p>
            <h2 className="da-section__title">
              Coach notes {ai?.confidence_score != null ? `· conf ${ai.confidence_score}` : ""}
            </h2>
          </div>
          {ai ? (
            <div className="ds-muted" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <p><strong>Summary:</strong> {ai.summary}</p>
              <div>
                <strong>Strengths</strong>
                <ul>{(ai.strengths || []).map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
              </div>
              <div>
                <strong>Weaknesses</strong>
                <ul>{(ai.weaknesses || []).map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
              </div>
              <div>
                <strong>Mistakes</strong>
                <ul>{(ai.mistakes || []).map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
              </div>
              <div>
                <strong>Top 5 improvements</strong>
                <ol>{(ai.recommendations || ai.suggestions || []).slice(0, 5).map((s: string, i: number) => <li key={i}>{s}</li>)}</ol>
              </div>
              <div>
                <strong>Risk observations</strong>
                <ul>{(ai.risk_observations || []).map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
              </div>
              <p style={{ fontSize: 12, opacity: 0.7 }}>Source: {ai.source || "heuristic"}</p>
            </div>
          ) : (
            <ChartSkeleton height={160} />
          )}
        </div>

        <div className="da-section">
          <div className="da-section__header">
            <p className="da-section__label">Daily journal</p>
            <h2 className="da-section__title">
              Notes {journalSaving ? "· saving..." : journalMsg ? `· ${journalMsg}` : "· auto-save"}
            </h2>
          </div>
          <label className="filter-field" style={{ display: "block", marginBottom: 8 }}>
            <span>Today&apos;s observations</span>
            <textarea
              rows={3}
              className="da-textarea"
              value={journal.observations}
              onChange={(e) => updateJournal("observations", e.target.value)}
            />
          </label>
          <label className="filter-field" style={{ display: "block", marginBottom: 8 }}>
            <span>Mistakes</span>
            <textarea
              rows={2}
              className="da-textarea"
              value={journal.mistakes}
              onChange={(e) => updateJournal("mistakes", e.target.value)}
            />
          </label>
          <label className="filter-field" style={{ display: "block", marginBottom: 8 }}>
            <span>Lessons</span>
            <textarea
              rows={2}
              className="da-textarea"
              value={journal.lessons}
              onChange={(e) => updateJournal("lessons", e.target.value)}
            />
          </label>
          <label className="filter-field" style={{ display: "block" }}>
            <span>Tomorrow&apos;s plan</span>
            <textarea
              rows={2}
              className="da-textarea"
              value={journal.tomorrow_plan}
              onChange={(e) => updateJournal("tomorrow_plan", e.target.value)}
            />
          </label>
        </div>

        <div className="da-section">
          <div className="da-section__header">
            <p className="da-section__label">Market context</p>
            <h2 className="da-section__title">Session backdrop</h2>
          </div>
          <div className="ds-muted">
            <div>Nifty: {data?.market_context?.nifty ?? "—"}</div>
            <div>Bank Nifty: {data?.market_context?.bank_nifty ?? "—"}</div>
            <div>VIX: {data?.market_context?.vix ?? "—"}</div>
            <div>Breadth: {data?.market_context?.market_breadth ?? "—"}</div>
            <div>Sector strength: {data?.market_context?.sector_strength ?? "—"}</div>
            <p style={{ marginTop: 8, fontSize: 12 }}>{data?.market_context?.note}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

export default memo(DailyAnalyticsPanel);
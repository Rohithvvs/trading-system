/**
 * Daily Analytics — professional trading journal view (user-scoped).
 * Shell + skeletons first; data loads async. Charts lazy-rendered when data arrives.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchDailyAnalytics,
  saveDailyJournal,
  type DailyAnalyticsPeriod,
} from "../api";
import { getCached, CACHE_KEYS } from "../utils/appCache";
import { MetricCardSkeleton, ChartSkeleton, TableSkeleton } from "./Skeleton";

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

  // Charts — destroy/recreate when data changes
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
          options: { responsive: true, plugins: { legend: { display: false } } },
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
          options: { responsive: true, plugins: { legend: { display: false } } },
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
          options: { responsive: true },
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
          options: { responsive: true },
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
          options: { responsive: true },
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

  function exportJsonAsExcelish() {
    // Lightweight: download JSON (Excel can open CSV; full xlsx needs extra dep)
    if (!data) return;
    exportCsv();
  }

  function exportPdf() {
    // Print-friendly view
    window.print();
  }

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

  return (
    <section className="daily-analytics" data-testid="daily-analytics-panel">
      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-header" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
          <div>
            <p className="section-label">Daily Analytics</p>
            <h2 style={{ margin: 0 }}>Session performance journal</h2>
            <p className="muted-copy" style={{ marginTop: 4 }}>
              {data?.range_label ? `Range: ${data.range_label}` : "Loading range…"} · User-isolated paper book
            </p>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            {(
              [
                ["today", "Today"],
                ["yesterday", "Yesterday"],
                ["week", "This Week"],
                ["month", "This Month"],
                ["custom", "Custom"],
              ] as const
            ).map(([id, label]) => (
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
            <button type="button" className="button ghost-button" onClick={() => void load(true)}>
              Refresh
            </button>
            <button type="button" className="button ghost-button" onClick={exportCsv} disabled={!data}>
              CSV
            </button>
            <button type="button" className="button ghost-button" onClick={exportJsonAsExcelish} disabled={!data}>
              Excel
            </button>
            <button type="button" className="button ghost-button" onClick={exportPdf} disabled={!data}>
              PDF
            </button>
          </div>
        </div>
      </div>

      {error && !data ? (
        <section className="panel error-state">
          <h2>Failed to load Daily Analytics</h2>
          <p>{error}</p>
          <button type="button" className="button primary-button" onClick={() => void load(true)}>
            Retry
          </button>
        </section>
      ) : null}

      {/* Trading score + overview */}
      <section className="panel" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "stretch" }}>
          <div
            className={`metric-card ${score ? scoreClass(score.score) : ""}`}
            style={{ minWidth: 160, textAlign: "center" }}
            data-testid="daily-trading-score"
          >
            <span>Daily Trading Score</span>
            {loading && !score ? (
              <div className="app-skel" style={{ height: 48, marginTop: 8 }} />
            ) : (
              <>
                <strong style={{ fontSize: "2rem" }}>{score?.score ?? "—"}</strong>
                <p>{score?.label ?? "—"}</p>
              </>
            )}
          </div>
          <div style={{ flex: 1, minWidth: 240 }}>
            {loading && !ov ? (
              <MetricCardSkeleton count={8} />
            ) : (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                {metricTiles.map(([label, value]) => (
                  <div key={String(label)} className="metric-card" style={{ minWidth: 120, flex: "1 1 120px" }}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Trade summary + performance + portfolio */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginBottom: 12 }}>
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">Trade summary</p>
              <h2>Activity</h2>
            </div>
          </div>
          {loading && !summary ? (
            <MetricCardSkeleton count={4} />
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div className="metric-card"><span>Total trades</span><strong>{summary?.total_trades ?? "—"}</strong></div>
              <div className="metric-card"><span>Executed</span><strong>{summary?.executed_orders ?? "—"}</strong></div>
              <div className="metric-card"><span>Pending</span><strong>{summary?.pending_orders ?? "—"}</strong></div>
              <div className="metric-card"><span>Cancelled</span><strong>{summary?.cancelled_orders ?? "—"}</strong></div>
              <div className="metric-card"><span>Rejected</span><strong>{summary?.rejected_orders ?? "—"}</strong></div>
              <div className="metric-card"><span>Avg hold (min)</span><strong>{summary?.average_holding_minutes ?? "—"}</strong></div>
              <div className="metric-card"><span>Avg size</span><strong>{money(summary?.average_position_size)}</strong></div>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">Performance</p>
              <h2>Edge metrics</h2>
            </div>
          </div>
          {loading && !perf ? (
            <MetricCardSkeleton count={6} />
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div className="metric-card"><span>Net profit</span><strong>{money(perf?.net_profit)}</strong></div>
              <div className="metric-card"><span>Gross profit</span><strong>{money(perf?.gross_profit)}</strong></div>
              <div className="metric-card"><span>Gross loss</span><strong>{money(perf?.gross_loss)}</strong></div>
              <div className="metric-card"><span>Profit factor</span><strong>{perf?.profit_factor ?? "—"}</strong></div>
              <div className="metric-card"><span>Win rate</span><strong>{pct(perf?.win_rate)}</strong></div>
              <div className="metric-card"><span>Loss rate</span><strong>{pct(perf?.loss_rate)}</strong></div>
              <div className="metric-card"><span>R:R</span><strong>{perf?.risk_reward_ratio ?? "—"}</strong></div>
              <div className="metric-card"><span>Expectancy</span><strong>{money(perf?.expectancy)}</strong></div>
              <div className="metric-card"><span>Max DD</span><strong>{money(perf?.maximum_drawdown)}</strong></div>
              <div className="metric-card"><span>Sharpe</span><strong>{perf?.sharpe_ratio ?? "—"}</strong></div>
              <div className="metric-card"><span>Sortino</span><strong>{perf?.sortino_ratio ?? "—"}</strong></div>
              <div className="metric-card"><span>Recovery</span><strong>{perf?.recovery_factor ?? "—"}</strong></div>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">Portfolio</p>
              <h2>Allocation</h2>
            </div>
          </div>
          {loading && !port ? (
            <MetricCardSkeleton count={4} />
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div className="metric-card"><span>Portfolio value</span><strong>{money(port?.portfolio_value)}</strong></div>
              <div className="metric-card"><span>Cash</span><strong>{money(port?.cash_balance)}</strong></div>
              <div className="metric-card"><span>Invested</span><strong>{money(port?.invested_amount)}</strong></div>
              <div className="metric-card"><span>Allocation %</span><strong>{pct(port?.allocation_pct)}</strong></div>
              <div className="metric-card"><span>Utilization %</span><strong>{pct(port?.utilization_pct)}</strong></div>
            </div>
          )}
        </section>
      </div>

      {/* Charts */}
      <section className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-header">
          <div>
            <p className="section-label">Charts</p>
            <h2>Visual analysis</h2>
          </div>
        </div>
        {loading && !data ? (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <ChartSkeleton height={200} />
            <ChartSkeleton height={200} />
          </div>
        ) : (
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <div className="panel" style={{ flex: "1 1 320px", minWidth: 280 }}>
              <p className="section-label">Daily equity curve</p>
              <canvas ref={equityRef} height={160} />
            </div>
            <div className="panel" style={{ flex: "1 1 320px", minWidth: 280 }}>
              <p className="section-label">Hourly P&L</p>
              <canvas ref={hourlyRef} height={160} />
            </div>
            <div className="panel" style={{ width: 240 }}>
              <p className="section-label">Win / Loss</p>
              <canvas ref={pieRef} height={160} />
            </div>
            <div className="panel" style={{ width: 240 }}>
              <p className="section-label">Sector allocation</p>
              <canvas ref={sectorRef} height={160} />
            </div>
            <div className="panel" style={{ width: 240 }}>
              <p className="section-label">Capital usage</p>
              <canvas ref={capitalRef} height={160} />
            </div>
          </div>
        )}
      </section>

      {/* Best / worst / risk / time */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginBottom: 12 }}>
        <section className="panel">
          <p className="section-label">Best trade</p>
          <h2>{data?.best_trade?.symbol ?? "—"}</h2>
          {data?.best_trade ? (
            <div className="muted-copy">
              <div>Entry {money(data.best_trade.entry)} → Exit {money(data.best_trade.exit)}</div>
              <div>Profit {money(data.best_trade.profit)} ({pct(data.best_trade.return_pct)})</div>
              <div>Hold {data.best_trade.holding_time_minutes} min</div>
              <div>Reason: {data.best_trade.reason}</div>
            </div>
          ) : (
            <p className="muted-copy">No closed trades in range.</p>
          )}
        </section>
        <section className="panel">
          <p className="section-label">Worst trade</p>
          <h2>{data?.worst_trade?.symbol ?? "—"}</h2>
          {data?.worst_trade ? (
            <div className="muted-copy">
              <div>Loss {money(data.worst_trade.loss)}</div>
              <div>Hold {data.worst_trade.holding_time_minutes} min</div>
              <div>Mistake: {data.worst_trade.mistake}</div>
            </div>
          ) : (
            <p className="muted-copy">No closed trades in range.</p>
          )}
        </section>
        <section className="panel">
          <p className="section-label">Risk analysis</p>
          <h2>Exposure</h2>
          {risk ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div className="metric-card"><span>Largest</span><strong>{money(risk.largest_position)}</strong></div>
              <div className="metric-card"><span>Smallest</span><strong>{money(risk.smallest_position)}</strong></div>
              <div className="metric-card"><span>Risk %</span><strong>{pct(risk.risk_pct)}</strong></div>
              <div className="metric-card"><span>Exposure</span><strong>{money(risk.exposure)}</strong></div>
              <div className="metric-card"><span>Concentration</span><strong>{pct(risk.capital_concentration)}</strong></div>
            </div>
          ) : (
            <MetricCardSkeleton count={3} />
          )}
        </section>
        <section className="panel">
          <p className="section-label">Emotional analysis</p>
          <h2>Process scores</h2>
          {emotional ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div className="metric-card"><span>Discipline</span><strong>{emotional.discipline}</strong></div>
              <div className="metric-card"><span>Patience</span><strong>{emotional.patience}</strong></div>
              <div className="metric-card"><span>Risk control</span><strong>{emotional.risk_control}</strong></div>
              <div className="metric-card"><span>Execution</span><strong>{emotional.execution_quality}</strong></div>
              <div className="metric-card"><span>Consistency</span><strong>{emotional.consistency}</strong></div>
            </div>
          ) : (
            <MetricCardSkeleton count={3} />
          )}
        </section>
      </div>

      {/* Time analysis */}
      <section className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-header">
          <div>
            <p className="section-label">Time analysis</p>
            <h2>Trades by session slot</h2>
          </div>
        </div>
        {loading && !data ? (
          <TableSkeleton rows={3} cols={3} />
        ) : (
          <div className="table-scroll">
            <table className="candidate-table">
              <thead>
                <tr>
                  <th>Slot</th>
                  <th>Trades</th>
                  <th>P&L</th>
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
      </section>

      {/* Sector + symbols */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12, marginBottom: 12 }}>
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">Sector analysis</p>
              <h2>Allocation & P&L</h2>
            </div>
          </div>
          {loading && !data ? (
            <TableSkeleton rows={4} cols={5} />
          ) : (
            <div className="table-scroll">
              <table className="candidate-table">
                <thead>
                  <tr>
                    <th>Sector</th>
                    <th>Trades</th>
                    <th>Allocation</th>
                    <th>Profit</th>
                    <th>Loss</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.sector_analysis || []).map((s: any) => (
                    <tr key={s.sector}>
                      <td>{s.sector}</td>
                      <td>{s.trades}</td>
                      <td className="number-cell">{money(s.allocation)}</td>
                      <td className="number-cell">{money(s.profit)}</td>
                      <td className="number-cell">{money(s.loss)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">Symbol performance</p>
              <h2>Per-name results</h2>
            </div>
          </div>
          {loading && !data ? (
            <TableSkeleton rows={5} cols={6} />
          ) : (
            <div className="table-scroll">
              <table className="candidate-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>Qty</th>
                    <th>Return %</th>
                    <th>Hold</th>
                    <th>P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {(data?.symbol_performance || []).map((r: any, i: number) => (
                    <tr key={`${r.symbol}-${i}`}>
                      <td>{r.symbol}</td>
                      <td className="number-cell">{money(r.entry)}</td>
                      <td className="number-cell">{r.exit != null ? money(r.exit) : "—"}</td>
                      <td>{r.quantity}</td>
                      <td className="number-cell">{pct(r.return_pct)}</td>
                      <td>{r.holding_time_minutes}m</td>
                      <td className="number-cell">{money(r.pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {/* AI + Journal + Market */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 12, marginBottom: 12 }}>
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">AI insights</p>
              <h2>Coach notes {ai?.confidence_score != null ? `· conf ${ai.confidence_score}` : ""}</h2>
            </div>
          </div>
          {ai ? (
            <div className="muted-copy" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
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
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">Daily journal</p>
              <h2>
                Notes {journalSaving ? "· saving…" : journalMsg ? `· ${journalMsg}` : "· auto-save"}
              </h2>
            </div>
          </div>
          <label className="filter-field" style={{ display: "block", marginBottom: 8 }}>
            <span>Today&apos;s observations</span>
            <textarea
              rows={3}
              value={journal.observations}
              onChange={(e) => updateJournal("observations", e.target.value)}
              style={{ width: "100%", marginTop: 4 }}
            />
          </label>
          <label className="filter-field" style={{ display: "block", marginBottom: 8 }}>
            <span>Mistakes</span>
            <textarea
              rows={2}
              value={journal.mistakes}
              onChange={(e) => updateJournal("mistakes", e.target.value)}
              style={{ width: "100%", marginTop: 4 }}
            />
          </label>
          <label className="filter-field" style={{ display: "block", marginBottom: 8 }}>
            <span>Lessons</span>
            <textarea
              rows={2}
              value={journal.lessons}
              onChange={(e) => updateJournal("lessons", e.target.value)}
              style={{ width: "100%", marginTop: 4 }}
            />
          </label>
          <label className="filter-field" style={{ display: "block" }}>
            <span>Tomorrow&apos;s plan</span>
            <textarea
              rows={2}
              value={journal.tomorrow_plan}
              onChange={(e) => updateJournal("tomorrow_plan", e.target.value)}
              style={{ width: "100%", marginTop: 4 }}
            />
          </label>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="section-label">Market context</p>
              <h2>Session backdrop</h2>
            </div>
          </div>
          <div className="muted-copy">
            <div>Nifty: {data?.market_context?.nifty ?? "—"}</div>
            <div>Bank Nifty: {data?.market_context?.bank_nifty ?? "—"}</div>
            <div>VIX: {data?.market_context?.vix ?? "—"}</div>
            <div>Breadth: {data?.market_context?.market_breadth ?? "—"}</div>
            <div>Sector strength: {data?.market_context?.sector_strength ?? "—"}</div>
            <p style={{ marginTop: 8, fontSize: 12 }}>{data?.market_context?.note}</p>
          </div>
        </section>
      </div>
    </section>
  );
}

export default DailyAnalyticsPanel;

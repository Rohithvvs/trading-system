import { useEffect, useState } from "react";
import { fetchHoldings, fetchOrdersPage, fetchPositionsView } from "../../api_retail";
import { fetchAnalytics } from "../../api";

export function ReportsPage() {
  const [summary, setSummary] = useState<string>("Loading report data…");

  useEffect(() => {
    void (async () => {
      try {
        const [h, p, o, a] = await Promise.all([
          fetchHoldings(),
          fetchPositionsView(),
          fetchOrdersPage({ page: 1 }),
          fetchAnalytics().catch(() => null),
        ]);
        const lines = [
          `Holdings value: ₹${h.total_current_value.toLocaleString("en-IN")}`,
          `Invested: ₹${h.total_invested.toLocaleString("en-IN")}`,
          `Unrealized PnL: ₹${h.total_pnl.toLocaleString("en-IN")} (${h.total_pnl_pct.toFixed(2)}%)`,
          `Today's PnL: ₹${h.todays_pnl.toLocaleString("en-IN")}`,
          `Open positions: ${p.open.length} · MTM ₹${p.total_mtm.toLocaleString("en-IN")}`,
          `Orders: ${o.total} (pending ${o.pending}, filled ${o.executed}, rejected ${o.rejected}, cancelled ${o.cancelled})`,
        ];
        if (a && typeof a === "object") {
          lines.push(`Analytics loaded: ${Object.keys(a as object).length} fields`);
        }
        setSummary(lines.join("\n"));
      } catch (e) {
        setSummary(e instanceof Error ? e.message : "Failed to load report");
      }
    })();
  }, []);

  function downloadTxt() {
    const blob = new Blob([summary], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `portfolio-report-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadCsv() {
    const rows = summary.split("\n").map((line) => {
      const [k, ...rest] = line.split(":");
      return `"${k.trim()}","${rest.join(":").trim()}"`;
    });
    const blob = new Blob([["metric,value", ...rows].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `portfolio-report-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Reports</p>
            <h2>Portfolio statement</h2>
          </div>
          <div className="scanner-actions" style={{ margin: 0 }}>
            <button type="button" className="button ghost-button" onClick={downloadTxt}>Export TXT</button>
            <button type="button" className="button primary-button" onClick={downloadCsv}>Export CSV</button>
          </div>
        </div>
        <pre className="report-pre" style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", margin: 0 }}>{summary}</pre>
      </section>
    </div>
  );
}

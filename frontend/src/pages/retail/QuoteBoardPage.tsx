import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchQuoteBoard, type QuoteBoardItem } from "../../api_retail";

const COLS = [
  { key: "symbol", label: "Symbol" },
  { key: "ltp", label: "LTP" },
  { key: "change", label: "Change" },
  { key: "change_pct", label: "% Chg" },
  { key: "open", label: "Open" },
  { key: "high", label: "High" },
  { key: "low", label: "Low" },
  { key: "close", label: "Close" },
  { key: "vwap", label: "VWAP" },
  { key: "volume", label: "Volume" },
  { key: "bid", label: "Bid" },
  { key: "ask", label: "Ask" },
  { key: "bid_qty", label: "Bid Qty" },
  { key: "ask_qty", label: "Ask Qty" },
  { key: "upper_circuit", label: "UC" },
  { key: "lower_circuit", label: "LC" },
  { key: "market_status", label: "Status" },
] as const;

const ROW_H = 40;
const VIEWPORT_H = 560;

export function QuoteBoardPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<QuoteBoardItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("");
  const [sortBy, setSortBy] = useState("symbol");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [status, setStatus] = useState("UNKNOWN");
  const [scrollTop, setScrollTop] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void fetchQuoteBoard({
        search: search || undefined,
        sector: sector || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: 100,
      })
        .then((r) => {
          if (cancelled) return;
          setItems(r.items);
          setTotal(r.total);
          setStatus(r.market_status);
        })
        .catch((e: Error) => {
          if (!cancelled) setError(e.message);
        });
    };
    load();
    const id = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [search, sector, sortBy, sortDir, page]);

  const start = Math.floor(scrollTop / ROW_H);
  const visibleCount = Math.ceil(VIEWPORT_H / ROW_H) + 5;
  const slice = items.slice(start, start + visibleCount);
  const padTop = start * ROW_H;
  const padBottom = Math.max(0, (items.length - start - slice.length) * ROW_H);

  function toggleSort(key: string) {
    if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortBy(key);
      setSortDir("asc");
    }
  }

  function fmt(v: number | null | undefined, digits = 2) {
    if (v == null || Number.isNaN(v)) return "—";
    return Number(v).toLocaleString("en-IN", { maximumFractionDigits: digits });
  }

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Live quote board · {status}</p>
            <h2>Market quotes</h2>
          </div>
          <div className="scanner-actions" style={{ margin: 0 }}>
            <input placeholder="Search" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
            <input placeholder="Sector filter" value={sector} onChange={(e) => { setSector(e.target.value); setPage(1); }} />
            <span className="muted-copy">{total} symbols</span>
          </div>
        </div>
        {error ? <div className="warning-box">{error}</div> : null}
        <div className="quote-board">
          <div className="quote-board-head sticky-head">
            <table className="data-table">
              <thead>
                <tr>
                  {COLS.map((c) => (
                    <th key={c.key} onClick={() => toggleSort(c.key)} style={{ cursor: "pointer" }}>
                      {c.label}
                      {sortBy === c.key ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
            </table>
          </div>
          <div
            ref={bodyRef}
            className="quote-board-body"
            style={{ height: VIEWPORT_H, overflow: "auto" }}
            onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
          >
            <div style={{ height: padTop }} />
            <table className="data-table">
              <tbody>
                {slice.map((row) => {
                  const pct = row.change_pct ?? 0;
                  return (
                    <tr
                      key={row.symbol}
                      style={{ height: ROW_H }}
                      className={pct >= 0 ? "flash-up" : "flash-down"}
                      onClick={() => navigate(`/chart/${row.symbol}`)}
                    >
                      <td>
                        <strong>{row.symbol}</strong>
                        <div className="muted-copy">{row.company_name}</div>
                      </td>
                      <td>{fmt(row.ltp)}</td>
                      <td className={pct >= 0 ? "pos" : "neg"}>{fmt(row.change)}</td>
                      <td className={pct >= 0 ? "pos" : "neg"}>{row.change_pct != null ? `${fmt(row.change_pct)}%` : "—"}</td>
                      <td>{fmt(row.open)}</td>
                      <td>{fmt(row.high)}</td>
                      <td>{fmt(row.low)}</td>
                      <td>{fmt(row.close)}</td>
                      <td>{fmt(row.vwap)}</td>
                      <td>{fmt(row.volume, 0)}</td>
                      <td>{fmt(row.bid)}</td>
                      <td>{fmt(row.ask)}</td>
                      <td>{fmt(row.bid_qty, 0)}</td>
                      <td>{fmt(row.ask_qty, 0)}</td>
                      <td>{fmt(row.upper_circuit)}</td>
                      <td>{fmt(row.lower_circuit)}</td>
                      <td>{row.market_status}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div style={{ height: padBottom }} />
          </div>
        </div>
        <div className="scanner-actions">
          <button type="button" className="button ghost-button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span className="muted-copy">Page {page}</span>
          <button type="button" className="button ghost-button" disabled={page * 100 >= total} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      </section>
    </div>
  );
}

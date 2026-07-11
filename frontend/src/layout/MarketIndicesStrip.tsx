import { useEffect, useState } from "react";
import { fetchIndices, type IndexQuote } from "../api_retail";

export function MarketIndicesStrip() {
  const [indices, setIndices] = useState<IndexQuote[]>([]);
  const [status, setStatus] = useState("UNKNOWN");

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      void fetchIndices()
        .then((r) => {
          if (cancelled) return;
          setIndices(r.indices);
          setStatus(r.market_status);
        })
        .catch(() => undefined);
    };
    load();
    const id = setInterval(load, 10000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="indices-strip" role="region" aria-label="Market indices">
      <span className={`indices-status ${status === "OPEN" ? "is-open" : "is-closed"}`}>{status}</span>
      <div className="indices-scroll">
        {indices.map((idx) => {
          const pct = idx.change_pct ?? 0;
          const positive = pct >= 0;
          return (
            <div key={idx.symbol} className={`index-chip ${positive ? "up" : "down"}`}>
              <div className="index-chip-main">
                <strong>{idx.label}</strong>
                <span className="index-ltp">{idx.ltp != null ? idx.ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "—"}</span>
              </div>
              <div className="index-chip-meta">
                <span className={positive ? "pos" : "neg"}>
                  {positive ? "+" : ""}
                  {pct.toFixed(2)}%
                </span>
                {idx.sparkline?.length ? (
                  <svg className="index-spark" viewBox="0 0 60 16" width={60} height={16} aria-hidden>
                    <polyline
                      fill="none"
                      stroke={positive ? "var(--positive)" : "var(--negative)"}
                      strokeWidth="1.5"
                      points={idx.sparkline
                        .map((v, i) => {
                          const min = Math.min(...idx.sparkline);
                          const max = Math.max(...idx.sparkline);
                          const range = max - min || 1;
                          const x = (i / Math.max(idx.sparkline.length - 1, 1)) * 60;
                          const y = 14 - ((v - min) / range) * 12;
                          return `${x},${y}`;
                        })
                        .join(" ")}
                    />
                  </svg>
                ) : null}
              </div>
            </div>
          );
        })}
        {!indices.length ? <span className="muted-copy">Loading indices…</span> : null}
      </div>
    </div>
  );
}

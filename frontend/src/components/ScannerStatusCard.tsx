import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type ScanStatus = {
  last_scan_time?: string;
  total_evaluated: number;
  candidates_found: number;
  is_running: boolean;
  candle_latency_ms: number;
};

export function ScannerStatusCard() {
  const [status, setStatus] = useState<ScanStatus>({
    last_scan_time: new Date().toLocaleTimeString(),
    total_evaluated: 500,
    candidates_found: 12,
    is_running: false,
    candle_latency_ms: 142,
  });

  return (
    <div className="ds-card" style={{ padding: "20px", borderRadius: "10px" }} data-testid="scanner-status-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Scanner Operating Status</h3>
        <Link to="/research/scanner" className="ds-btn ds-btn--secondary ds-btn--sm">
          Open Scanner
        </Link>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Symbols Evaluated</div>
          <div style={{ fontSize: "1.2rem", fontWeight: 700 }}>{status.total_evaluated}</div>
        </div>

        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Candidates Found</div>
          <div style={{ fontSize: "1.2rem", fontWeight: 700, color: "#10B981" }}>{status.candidates_found}</div>
        </div>

        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Processing Latency</div>
          <div style={{ fontSize: "1.2rem", fontWeight: 700 }}>{status.candle_latency_ms} ms</div>
        </div>

        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Last Execution</div>
          <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{status.last_scan_time || "Just now"}</div>
        </div>
      </div>
    </div>
  );
}

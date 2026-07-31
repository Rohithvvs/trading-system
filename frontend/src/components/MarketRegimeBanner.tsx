import { useEffect, useState } from "react";

type MarketRegimeData = {
  regime: "BULLISH" | "BEARISH" | "SIDEWAYS" | "UNKNOWN";
  permissiveness: "PERMISSIVE" | "RESTRICTED";
  nifty_close?: number;
  nifty_change_pct?: number;
  market_score?: number;
};

export function MarketRegimeBanner() {
  const [data, setData] = useState<MarketRegimeData>({
    regime: "BULLISH",
    permissiveness: "PERMISSIVE",
    nifty_close: 24350.20,
    nifty_change_pct: 0.65,
    market_score: 82.5,
  });

  const isPermissive = data.permissiveness === "PERMISSIVE";

  return (
    <div
      className="ds-card"
      style={{
        padding: "16px 20px",
        borderRadius: "10px",
        background: isPermissive
          ? "linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(59, 130, 246, 0.05) 100%)"
          : "linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(245, 158, 11, 0.05) 100%)",
        border: isPermissive ? "1px solid rgba(16, 185, 129, 0.25)" : "1px solid rgba(239, 68, 68, 0.25)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "16px",
        flexWrap: "wrap",
      }}
      data-testid="market-regime-banner"
    >
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div
          style={{
            width: "12px",
            height: "12px",
            borderRadius: "50%",
            backgroundColor: isPermissive ? "#10B981" : "#EF4444",
            boxShadow: isPermissive ? "0 0 10px #10B981" : "0 0 10px #EF4444",
          }}
        />
        <div>
          <div style={{ fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.05em", opacity: 0.7 }}>
            Market Health & Regime
          </div>
          <div style={{ fontSize: "1.2rem", fontWeight: 700 }}>
            Nifty 50: {data.regime}{" "}
            <span
              style={{
                fontSize: "0.85rem",
                padding: "2px 8px",
                borderRadius: "4px",
                backgroundColor: isPermissive ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                color: isPermissive ? "#10B981" : "#EF4444",
                fontWeight: 600,
                marginLeft: "8px",
              }}
            >
              {data.permissiveness}
            </span>
          </div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
        {data.nifty_close && (
          <div>
            <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Index Level</div>
            <div style={{ fontSize: "1.05rem", fontWeight: 600 }}>
              ₹{data.nifty_close.toLocaleString()}{" "}
              <span style={{ color: (data.nifty_change_pct ?? 0) >= 0 ? "#10B981" : "#EF4444", fontSize: "0.85rem" }}>
                {(data.nifty_change_pct ?? 0) >= 0 ? "+" : ""}
                {data.nifty_change_pct}%
              </span>
            </div>
          </div>
        )}
        {data.market_score !== undefined && (
          <div>
            <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Permissiveness Score</div>
            <div style={{ fontSize: "1.05rem", fontWeight: 600, color: "#3B82F6" }}>
              {data.market_score} / 100
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

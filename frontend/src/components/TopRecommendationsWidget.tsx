import { useState } from "react";
import { useNavigate } from "react-router-dom";

export type Recommendation = {
  id: string;
  symbol: string;
  signal_type: "BUY" | "SELL";
  conviction_score: number;
  entry_target: number;
  stop_loss: number;
  target_price: number;
  ai_rationale: string;
};

type Props = {
  onTradeClick?: (rec: Recommendation) => void;
};

const MOCK_RECOMMENDATIONS: Recommendation[] = [
  {
    id: "rec_1",
    symbol: "TCS",
    signal_type: "BUY",
    conviction_score: 92.0,
    entry_target: 4150.0,
    stop_loss: 4020.0,
    target_price: 4350.0,
    ai_rationale: "Strong sector relative strength with EMA50 breakout and bullish MACD crossover.",
  },
  {
    id: "rec_2",
    symbol: "RELIANCE",
    signal_type: "BUY",
    conviction_score: 88.5,
    entry_target: 2980.5,
    stop_loss: 2910.0,
    target_price: 3120.0,
    ai_rationale: "Supertrend buy signal confirmed with volume expansion above 200 EMA.",
  },
  {
    id: "rec_3",
    symbol: "INFY",
    signal_type: "BUY",
    conviction_score: 84.0,
    entry_target: 1840.0,
    stop_loss: 1790.0,
    target_price: 1950.0,
    ai_rationale: "Consolidation pattern breakout aligned with IT index relative strength.",
  },
];

export function TopRecommendationsWidget({ onTradeClick }: Props) {
  const navigate = useNavigate();
  const [recommendations] = useState<Recommendation[]>(MOCK_RECOMMENDATIONS);

  return (
    <div className="ds-card" style={{ padding: "20px", borderRadius: "10px" }} data-testid="top-recommendations-widget">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>
          Today's High-Conviction AI Recommendations
        </h3>
        <span style={{ fontSize: "0.75rem", background: "rgba(59, 130, 246, 0.15)", color: "#3B82F6", padding: "4px 8px", borderRadius: "4px", fontWeight: 600 }}>
          Score &gt; 80
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {recommendations.map((rec) => (
          <div
            key={rec.id}
            style={{
              padding: "14px 16px",
              borderRadius: "8px",
              background: "rgba(255, 255, 255, 0.02)",
              border: "1px solid rgba(255, 255, 255, 0.06)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "16px",
              flexWrap: "wrap",
            }}
          >
            <div style={{ flex: 1, minWidth: "220px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "1.1rem", fontWeight: 700 }}>{rec.symbol}</span>
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    padding: "2px 6px",
                    borderRadius: "4px",
                    backgroundColor: rec.signal_type === "BUY" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                    color: rec.signal_type === "BUY" ? "#10B981" : "#EF4444",
                  }}
                >
                  {rec.signal_type}
                </span>
                <span style={{ fontSize: "0.85rem", fontWeight: 600, color: "#3B82F6" }}>
                  Score: {rec.conviction_score}
                </span>
              </div>
              <div style={{ fontSize: "0.8rem", opacity: 0.75, marginTop: "4px" }}>
                {rec.ai_rationale}
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
              <div style={{ textAlign: "right", fontSize: "0.85rem" }}>
                <div>Target: <strong style={{ color: "#10B981" }}>₹{rec.target_price}</strong></div>
                <div style={{ opacity: 0.7 }}>Stop: ₹{rec.stop_loss}</div>
              </div>

              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  type="button"
                  className="ds-btn ds-btn--secondary ds-btn--sm"
                  onClick={() => navigate(`/research/workstation?symbol=${rec.symbol}`)}
                  title="Inspect technicals & AI rationale"
                >
                  Inspect
                </button>
                <button
                  type="button"
                  className="ds-btn ds-btn--buy ds-btn--sm"
                  onClick={() => onTradeClick?.(rec)}
                  title="Trade via Order Drawer"
                >
                  Trade
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

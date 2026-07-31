type Props = {
  symbol: string;
};

export function AIRationaleCard({ symbol }: Props) {
  return (
    <div className="ds-card" style={{ padding: "20px", borderRadius: "10px" }} data-testid="ai-rationale-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>AI Agent Conviction & Rationale</h3>
        <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "#10B981", background: "rgba(16, 185, 129, 0.15)", padding: "2px 8px", borderRadius: "4px" }}>
          Conviction: 92/100
        </span>
      </div>

      <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "14px", borderRadius: "8px", fontSize: "0.9rem", lineHeight: "1.5" }}>
        <p style={{ margin: "0 0 10px 0" }}>
          <strong>Technical Synthesis:</strong> {symbol} exhibits strong institutional accumulation above the 50-day EMA. The daily MACD histogram crossed above zero while relative strength against Nifty 50 is outperforming by +1.4% over 5 sessions.
        </p>
        <p style={{ margin: 0, opacity: 0.85 }}>
          <strong>Risk Assessment:</strong> Primary stop-loss at 5-day swing low. Risk-to-reward ratio estimated at 1:2.4 with strong resistance at target level.
        </p>
      </div>
    </div>
  );
}

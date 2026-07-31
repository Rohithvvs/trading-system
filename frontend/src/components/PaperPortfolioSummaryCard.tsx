import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

type AccountSummary = {
  current_balance: number;
  open_pnl: number;
  day_pnl: number;
  open_positions_count: number;
  win_rate: number;
};

export function PaperPortfolioSummaryCard() {
  const [account, setAccount] = useState<AccountSummary>({
    current_balance: 1054200.0,
    open_pnl: 12300.0,
    day_pnl: 5400.0,
    open_positions_count: 3,
    win_rate: 68.4,
  });

  return (
    <div className="ds-card" style={{ padding: "20px", borderRadius: "10px" }} data-testid="paper-portfolio-summary-card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 600 }}>Paper Portfolio Summary</h3>
        <Link to="/trading/paper-desk" className="ds-btn ds-btn--secondary ds-btn--sm">
          Open Paper Desk
        </Link>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "12px" }}>
        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Account Equity</div>
          <div style={{ fontSize: "1.15rem", fontWeight: 700 }}>₹{account.current_balance.toLocaleString()}</div>
        </div>

        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Unrealized P&amp;L</div>
          <div style={{ fontSize: "1.15rem", fontWeight: 700, color: account.open_pnl >= 0 ? "#10B981" : "#EF4444" }}>
            {account.open_pnl >= 0 ? "+" : ""}₹{account.open_pnl.toLocaleString()}
          </div>
        </div>

        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Day Realized P&amp;L</div>
          <div style={{ fontSize: "1.15rem", fontWeight: 700, color: account.day_pnl >= 0 ? "#10B981" : "#EF4444" }}>
            {account.day_pnl >= 0 ? "+" : ""}₹{account.day_pnl.toLocaleString()}
          </div>
        </div>

        <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "12px", borderRadius: "8px" }}>
          <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Win Rate</div>
          <div style={{ fontSize: "1.15rem", fontWeight: 700, color: "#3B82F6" }}>{account.win_rate}%</div>
        </div>
      </div>
    </div>
  );
}

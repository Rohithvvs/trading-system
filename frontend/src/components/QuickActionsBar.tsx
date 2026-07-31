import { useNavigate } from "react-router-dom";

export function QuickActionsBar() {
  const navigate = useNavigate();

  return (
    <div
      className="quick-actions-bar"
      style={{
        display: "flex",
        gap: "8px",
        flexWrap: "wrap",
        alignItems: "center",
      }}
    >
      <button
        type="button"
        className="ds-btn ds-btn--primary ds-btn--sm"
        onClick={() => navigate("/research/scanner")}
        data-testid="quick-action-scanner"
      >
        Opportunity Scanner
      </button>
      <button
        type="button"
        className="ds-btn ds-btn--secondary ds-btn--sm"
        onClick={() => navigate("/paper-order")}
        data-testid="quick-action-order"
      >
        + New Order Ticket
      </button>
      <button
        type="button"
        className="ds-btn ds-btn--ghost ds-btn--sm"
        onClick={() => navigate("/trading/paper-desk")}
        data-testid="quick-action-portfolio"
      >
        Paper Desk
      </button>
      <button
        type="button"
        className="ds-btn ds-btn--ghost ds-btn--sm"
        onClick={() => navigate("/system/logs")}
        data-testid="quick-action-logs"
      >
        System Logs
      </button>
    </div>
  );
}

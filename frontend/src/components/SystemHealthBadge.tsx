export function SystemHealthBadge() {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "4px 10px",
        borderRadius: "20px",
        backgroundColor: "rgba(16, 185, 129, 0.15)",
        color: "#10B981",
        fontSize: "0.75rem",
        fontWeight: 600,
      }}
      data-testid="system-health-badge"
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          backgroundColor: "#10B981",
          boxShadow: "0 0 6px #10B981",
        }}
      />
      Broker Stream: Active
    </div>
  );
}

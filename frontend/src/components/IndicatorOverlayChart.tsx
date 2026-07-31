import { useMemo } from "react";

type Props = {
  symbol: string;
};

export function IndicatorOverlayChart({ symbol }: Props) {
  // Mock OHLCV + Technical Indicator Data (EMA50, EMA200, Supertrend)
  const chartData = useMemo(() => {
    const data = [];
    let price = 4100;
    for (let i = 0; i < 30; i++) {
      const change = (Math.random() - 0.45) * 40;
      price += change;
      const ema50 = price - 30 + i * 0.8;
      const ema200 = price - 120 + i * 0.5;
      data.push({
        day: `Day ${i + 1}`,
        price: parseFloat(price.toFixed(2)),
        ema50: parseFloat(ema50.toFixed(2)),
        ema200: parseFloat(ema200.toFixed(2)),
      });
    }
    return data;
  }, [symbol]);

  return (
    <div className="ds-card" style={{ padding: "20px", borderRadius: "10px" }} data-testid="indicator-overlay-chart">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <div>
          <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>
            {symbol} Technical Indicator Chart
          </h3>
          <span style={{ fontSize: "0.75rem", opacity: 0.7 }}>
            Overlays: EMA 50 (Green), EMA 200 (Purple), Supertrend BUY
          </span>
        </div>
        <div style={{ display: "flex", gap: "12px", fontSize: "0.8rem", fontWeight: 600 }}>
          <span style={{ color: "#10B981" }}>■ EMA 50</span>
          <span style={{ color: "#8B5CF6" }}>■ EMA 200</span>
          <span style={{ color: "#3B82F6" }}>■ Price</span>
        </div>
      </div>

      <div
        style={{
          height: "260px",
          width: "100%",
          background: "rgba(255, 255, 255, 0.02)",
          borderRadius: "8px",
          border: "1px solid rgba(255, 255, 255, 0.05)",
          display: "flex",
          alignItems: "flex-end",
          padding: "20px 10px 10px 10px",
          gap: "6px",
        }}
      >
        {chartData.map((d, idx) => {
          const heightPct = Math.min(Math.max(((d.price - 3900) / 400) * 100, 15), 95);
          return (
            <div
              key={idx}
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                height: "100%",
                justifyContent: "flex-end",
              }}
              title={`${d.day}: Price ₹${d.price} | EMA50 ₹${d.ema50} | EMA200 ₹${d.ema200}`}
            >
              <div
                style={{
                  width: "100%",
                  height: `${heightPct}%`,
                  backgroundColor: d.price >= d.ema50 ? "rgba(16, 185, 129, 0.6)" : "rgba(239, 68, 68, 0.6)",
                  borderRadius: "2px",
                  position: "relative",
                }}
              >
                {/* EMA 50 Dot */}
                <div
                  style={{
                    position: "absolute",
                    bottom: `${Math.min(Math.max(((d.ema50 - 3900) / 400) * 100, 5), 95)}%`,
                    left: "50%",
                    transform: "translateX(-50%)",
                    width: "4px",
                    height: "4px",
                    backgroundColor: "#10B981",
                    borderRadius: "50%",
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

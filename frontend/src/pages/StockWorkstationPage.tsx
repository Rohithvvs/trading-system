import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { AppShell } from "../layout/AppShell";
import { IndicatorOverlayChart } from "../components/IndicatorOverlayChart";
import { AIRationaleCard } from "../components/AIRationaleCard";
import { OrderDrawer } from "../components/OrderDrawer";

export function StockWorkstationPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const symbol = (searchParams.get("symbol") || "TCS").toUpperCase();
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <AppShell title={`Stock Research Workstation — ${symbol}`}>
      <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        {/* Top Header Card */}
        <div
          className="ds-card"
          style={{
            padding: "20px",
            borderRadius: "10px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "16px",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <h1 style={{ margin: 0, fontSize: "1.6rem", fontWeight: 800 }}>{symbol}</h1>
              <span style={{ fontSize: "0.85rem", background: "rgba(16, 185, 129, 0.2)", color: "#10B981", padding: "4px 8px", borderRadius: "4px", fontWeight: 700 }}>
                BUY SIGNAL
              </span>
            </div>
            <span style={{ fontSize: "0.85rem", opacity: 0.7 }}>Nifty 500 Component · IT Sector</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "0.75rem", opacity: 0.7 }}>Last Close</div>
              <div style={{ fontSize: "1.3rem", fontWeight: 700 }}>₹4,150.00</div>
            </div>

            <button
              type="button"
              className="ds-btn ds-btn--buy"
              onClick={() => setDrawerOpen(true)}
              style={{ padding: "10px 20px", fontWeight: 700 }}
            >
              Trade {symbol}
            </button>
          </div>
        </div>

        {/* 2-Column Main Surface */}
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: "20px" }}>
          <IndicatorOverlayChart symbol={symbol} />
          <AIRationaleCard symbol={symbol} />
        </div>
      </div>

      {/* Slide-out Order Drawer */}
      <OrderDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        initialData={{ symbol, side: "BUY" }}
      />
    </AppShell>
  );
}
export default StockWorkstationPage;

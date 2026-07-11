import { useEffect, useState } from "react";
import { previewOrder, type OrderPreviewResponse } from "../../api_retail";
import { placePaperOrder } from "../../api";

type Props = {
  symbol?: string;
  onPlaced?: () => void;
};

const ORDER_TYPES = ["MARKET", "LIMIT", "SL", "SL-M", "BRACKET", "COVER"] as const;
const PRODUCTS = ["CNC", "MIS", "NRML"] as const;
const VALIDITY = ["DAY", "IOC", "GTT"] as const;

export function ProfessionalOrderTicket({ symbol: initialSymbol = "", onPlaced }: Props) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [type, setType] = useState<(typeof ORDER_TYPES)[number]>("MARKET");
  const [product, setProduct] = useState<(typeof PRODUCTS)[number]>("CNC");
  const [validity, setValidity] = useState<(typeof VALIDITY)[number]>("DAY");
  const [qty, setQty] = useState(1);
  const [limitPrice, setLimitPrice] = useState<number | "">("");
  const [stopPrice, setStopPrice] = useState<number | "">("");
  const [stopLoss, setStopLoss] = useState<number | "">("");
  const [target, setTarget] = useState<number | "">("");
  const [preview, setPreview] = useState<OrderPreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setSymbol(initialSymbol);
  }, [initialSymbol]);

  useEffect(() => {
    if (!symbol || qty < 1) {
      setPreview(null);
      return;
    }
    const t = setTimeout(() => {
      void previewOrder({
        symbol,
        side,
        type,
        product_type: product,
        validity,
        qty,
        limit_price: limitPrice === "" ? null : Number(limitPrice),
        stop_price: stopPrice === "" ? null : Number(stopPrice),
        stop_loss: stopLoss === "" ? null : Number(stopLoss),
        target: target === "" ? null : Number(target),
      })
        .then(setPreview)
        .catch((e: Error) => setError(e.message));
    }, 300);
    return () => clearTimeout(t);
  }, [symbol, side, type, product, validity, qty, limitPrice, stopPrice, stopLoss, target]);

  async function execute() {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      // Map SL / SL-M to backend STOP / STOP_LIMIT
      let backendType: "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT" | "GTT" = "MARKET";
      if (type === "LIMIT") backendType = "LIMIT";
      else if (type === "SL" || type === "COVER") backendType = "STOP_LIMIT";
      else if (type === "SL-M") backendType = "STOP";
      else if (type === "BRACKET") backendType = "LIMIT";

      const res = await placePaperOrder(
        {
          symbol,
          side,
          type: backendType,
          productType: product,
          qty,
          limitPrice: limitPrice === "" ? null : Number(limitPrice),
          stopPrice: stopPrice === "" ? null : Number(stopPrice),
          stopLoss: stopLoss === "" ? null : Number(stopLoss),
          target: target === "" ? null : Number(target),
        },
        `retail-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      );
      setMessage(res.message || "Order placed");
      setConfirmOpen(false);
      onPlaced?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Order failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel order-ticket-pro">
      <div className="panel-header">
        <div>
          <p className="section-label">Order ticket</p>
          <h2>Professional ticket</h2>
        </div>
      </div>

      <div className="ot-side-toggle">
        <button type="button" className={side === "BUY" ? "is-buy" : ""} onClick={() => setSide("BUY")}>BUY</button>
        <button type="button" className={side === "SELL" ? "is-sell" : ""} onClick={() => setSide("SELL")}>SELL</button>
      </div>

      <label className="inline-field">
        <span>Symbol</span>
        <input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} data-testid="ot-symbol" />
      </label>

      <div className="ot-grid">
        <label className="inline-field">
          <span>Type</span>
          <select value={type} onChange={(e) => setType(e.target.value as typeof type)}>
            {ORDER_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="inline-field">
          <span>Product</span>
          <select value={product} onChange={(e) => setProduct(e.target.value as typeof product)}>
            {PRODUCTS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label className="inline-field">
          <span>Validity</span>
          <select value={validity} onChange={(e) => setValidity(e.target.value as typeof validity)}>
            {VALIDITY.map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </label>
        <label className="inline-field">
          <span>Qty</span>
          <input type="number" min={1} value={qty} onChange={(e) => setQty(Number(e.target.value) || 1)} />
        </label>
        {(type === "LIMIT" || type === "SL" || type === "BRACKET") && (
          <label className="inline-field">
            <span>Limit price</span>
            <input type="number" value={limitPrice} onChange={(e) => setLimitPrice(e.target.value === "" ? "" : Number(e.target.value))} />
          </label>
        )}
        {(type === "SL" || type === "SL-M" || type === "COVER") && (
          <label className="inline-field">
            <span>Trigger</span>
            <input type="number" value={stopPrice} onChange={(e) => setStopPrice(e.target.value === "" ? "" : Number(e.target.value))} />
          </label>
        )}
        <label className="inline-field">
          <span>Stop loss</span>
          <input type="number" value={stopLoss} onChange={(e) => setStopLoss(e.target.value === "" ? "" : Number(e.target.value))} />
        </label>
        <label className="inline-field">
          <span>Target</span>
          <input type="number" value={target} onChange={(e) => setTarget(e.target.value === "" ? "" : Number(e.target.value))} />
        </label>
      </div>

      {preview ? (
        <div className="ot-preview">
          <div className="ot-preview-row"><span>Est. price</span><strong>₹{preview.estimated_price.toFixed(2)}</strong></div>
          <div className="ot-preview-row"><span>Order value</span><strong>₹{preview.order_value.toLocaleString("en-IN")}</strong></div>
          <div className="ot-preview-row"><span>Brokerage</span><span>₹{preview.charges.brokerage.toFixed(2)}</span></div>
          <div className="ot-preview-row"><span>Taxes & fees</span><span>₹{preview.taxes_total.toFixed(2)}</span></div>
          <div className="ot-preview-row"><span>Total charges</span><span>₹{preview.charges.total_charges.toFixed(2)}</span></div>
          <div className="ot-preview-row"><span>Margin required</span><strong>₹{preview.margin_required.toLocaleString("en-IN")}</strong></div>
          <div className="ot-preview-row"><span>Funds required</span><strong>₹{preview.funds_required.toLocaleString("en-IN")}</strong></div>
          <div className="ot-preview-row"><span>Available</span><span>₹{preview.available_funds.toLocaleString("en-IN")}</span></div>
          {preview.risk_reward != null ? (
            <div className="ot-preview-row"><span>Risk:Reward</span><strong>1:{preview.risk_reward}</strong></div>
          ) : null}
          {preview.expected_pnl != null ? (
            <div className="ot-preview-row"><span>Expected PnL</span><strong className={preview.expected_pnl >= 0 ? "pos" : "neg"}>₹{preview.expected_pnl.toFixed(2)}</strong></div>
          ) : null}
          <div className="ot-risk-checks">
            {preview.risk_checks.map((c) => (
              <div key={c.code} className={c.passed ? "risk-pass" : "risk-fail"}>
                {c.passed ? "✓" : "✗"} {c.message}
              </div>
            ))}
          </div>
          {!preview.can_place && preview.reject_reasons.length ? (
            <div className="warning-box" style={{ marginTop: 8 }}>
              {preview.reject_reasons.map((r) => (
                <div key={r}>{r}</div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {error ? <div className="warning-box">{error}</div> : null}
      {message ? <div className="helper-chip" style={{ marginTop: 8 }}>{message}</div> : null}

      <button
        type="button"
        className={`button primary-button ${side === "SELL" ? "sell-btn" : ""}`}
        disabled={!preview?.can_place || loading || !symbol}
        onClick={() => setConfirmOpen(true)}
        data-testid="ot-submit"
      >
        {side} {symbol || "—"}
      </button>

      {confirmOpen ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <div className="confirm-modal">
            <h2>Confirm order</h2>
            <p>
              {side} {qty} {symbol} @ {type}
              {preview ? ` · Funds ₹${preview.funds_required.toLocaleString("en-IN")}` : ""}
            </p>
            <div className="modal-actions">
              <button type="button" className="button ghost-button" onClick={() => setConfirmOpen(false)}>Cancel</button>
              <button type="button" className="button primary-button" disabled={loading} onClick={() => void execute()}>
                {loading ? "Placing…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

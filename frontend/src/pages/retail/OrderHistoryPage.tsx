import { useEffect, useState } from "react";
import { fetchOrdersPage, type OrdersPageResponse } from "../../api_retail";

/** Dedicated order history route — filled / rejected / cancelled with pagination. */
export function OrderHistoryPage() {
  const [data, setData] = useState<OrdersPageResponse | null>(null);
  const [status, setStatus] = useState("FILLED");
  const [page, setPage] = useState(1);

  useEffect(() => {
    void fetchOrdersPage({ status: status || undefined, page }).then(setData).catch(() => undefined);
  }, [status, page]);

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Order history</p>
            <h2>Executed & terminal orders</h2>
          </div>
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="FILLED">Executed</option>
            <option value="REJECTED">Rejected</option>
            <option value="CANCELLED">Cancelled</option>
            <option value="">All</option>
          </select>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Type</th>
                <th>Qty</th>
                <th>Price</th>
                <th>Filled</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((o) => (
                <tr key={o.id}>
                  <td>{new Date(o.created_at).toLocaleString()}</td>
                  <td><strong>{o.symbol}</strong></td>
                  <td className={o.side === "BUY" ? "pos" : "neg"}>{o.side}</td>
                  <td>{o.type}</td>
                  <td>{o.qty}</td>
                  <td>{o.price ?? "—"}</td>
                  <td>{o.filled_price ?? "—"}</td>
                  <td>{o.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="scanner-actions">
          <button type="button" className="button ghost-button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span className="muted-copy">Page {page}</span>
          <button type="button" className="button ghost-button" onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      </section>
    </div>
  );
}

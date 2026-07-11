import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchOrdersPage, type OrdersPageResponse } from "../../api_retail";
import { cancelPaperOrder, placePaperOrder } from "../../api";
import { ProfessionalOrderTicket } from "../../components/retail/ProfessionalOrderTicket";

export function OrdersPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<OrdersPageResponse | null>(null);
  const [status, setStatus] = useState<string>("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [ticketSymbol, setTicketSymbol] = useState("");

  const reload = () => {
    void fetchOrdersPage({ status: status || undefined, search: search || undefined, page })
      .then(setData)
      .catch((e: Error) => setError(e.message));
  };

  useEffect(() => {
    reload();
    const id = setInterval(reload, 8000);
    return () => clearInterval(id);
  }, [status, search, page]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="dashboard-grid retail-page" style={{ gridTemplateColumns: "1fr 360px" }}>
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Orders</p>
            <h2>Order book</h2>
          </div>
          <div className="scanner-actions" style={{ margin: 0 }}>
            <span className="helper-chip">Pending {data?.pending ?? 0}</span>
            <span className="helper-chip">Executed {data?.executed ?? 0}</span>
            <span className="helper-chip">Rejected {data?.rejected ?? 0}</span>
            <span className="helper-chip">Cancelled {data?.cancelled ?? 0}</span>
          </div>
        </div>
        <div className="wl-toolbar">
          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All</option>
            <option value="PENDING">Pending</option>
            <option value="FILLED">Executed</option>
            <option value="REJECTED">Rejected</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
          <input placeholder="Search symbol" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
        </div>
        {error ? <div className="warning-box">{error}</div> : null}
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Type</th>
                <th>Product</th>
                <th>Qty</th>
                <th>Price</th>
                <th>Status</th>
                <th>Filled</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((o) => (
                <tr key={o.id}>
                  <td>{new Date(o.created_at).toLocaleString()}</td>
                  <td>
                    <button type="button" className="linkish" onClick={() => navigate(`/chart/${o.symbol}`)}>
                      <strong>{o.symbol}</strong>
                    </button>
                  </td>
                  <td className={o.side === "BUY" ? "pos" : "neg"}>{o.side}</td>
                  <td>{o.type}</td>
                  <td>{o.product_type || "—"}</td>
                  <td>{o.qty}</td>
                  <td>{o.price ?? "—"}</td>
                  <td>{o.status}</td>
                  <td>{o.filled_price ?? "—"}</td>
                  <td className="order-actions">
                    {o.status === "PENDING" ? (
                      <button type="button" className="button ghost-button" onClick={() => void cancelPaperOrder(o.id).then(reload)}>
                        Cancel
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="button ghost-button"
                      onClick={() => {
                        setTicketSymbol(o.symbol);
                      }}
                    >
                      Modify
                    </button>
                    <button
                      type="button"
                      className="button ghost-button"
                      onClick={() =>
                        void placePaperOrder(
                          {
                            symbol: o.symbol,
                            side: o.side as "BUY" | "SELL",
                            type: (o.type as "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT" | "GTT") || "MARKET",
                            qty: o.qty,
                            limitPrice: o.price,
                          },
                          crypto.randomUUID(),
                        ).then(reload)
                      }
                    >
                      Repeat
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data?.items.length ? <div className="empty-state"><p>No orders found.</p></div> : null}
        </div>
        <div className="scanner-actions">
          <button type="button" className="button ghost-button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <span className="muted-copy">Page {page} · {data?.total ?? 0} total</span>
          <button
            type="button"
            className="button ghost-button"
            disabled={!data || page * data.page_size >= data.total}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </button>
        </div>
      </section>
      <ProfessionalOrderTicket symbol={ticketSymbol} onPlaced={reload} />
    </div>
  );
}

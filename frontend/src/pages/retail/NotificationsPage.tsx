import { useEffect, useState } from "react";
import {
  deleteNotifications,
  fetchNotifications,
  markAllNotificationsRead,
  markNotifications,
  type NotificationItem,
} from "../../api_retail";

const CATEGORIES = [
  "",
  "price_alert",
  "scanner_alert",
  "order_update",
  "broker",
  "margin_call",
  "corporate_action",
  "news",
  "system",
];

export function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reload = () => {
    void fetchNotifications({ category: category || undefined, search: search || undefined })
      .then((r) => {
        setItems(r.items);
        setUnread(r.unread_count);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(() => {
    reload();
    const id = setInterval(reload, 15000);
    return () => clearInterval(id);
  }, [category, search]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Notification center</p>
            <h2>{unread} unread</h2>
          </div>
          <div className="scanner-actions" style={{ margin: 0 }}>
            <button type="button" className="button ghost-button" onClick={() => void markAllNotificationsRead().then(reload)}>
              Mark all read
            </button>
          </div>
        </div>
        <div className="wl-toolbar">
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c || "all"} value={c}>{c || "All categories"}</option>
            ))}
          </select>
          <input placeholder="Search notifications" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        {error ? <div className="warning-box">{error}</div> : null}
        <div className="notif-list">
          {items.map((n) => (
            <article key={n.id} className={`notif-item ${n.is_read ? "" : "is-unread"} level-${n.level}`}>
              <div className="notif-item-head">
                <span className="helper-chip">{n.category}</span>
                <strong>{n.title}</strong>
                <span className="muted-copy">{new Date(n.created_at).toLocaleString()}</span>
              </div>
              <p>{n.body}</p>
              {n.symbol ? <span className="helper-chip">{n.symbol}</span> : null}
              <div className="notif-item-actions">
                {!n.is_read ? (
                  <button type="button" className="button ghost-button" onClick={() => void markNotifications([n.id], true).then(reload)}>
                    Mark read
                  </button>
                ) : null}
                <button type="button" className="button ghost-button" onClick={() => void deleteNotifications([n.id]).then(reload)}>
                  Delete
                </button>
              </div>
            </article>
          ))}
          {!items.length ? <div className="empty-state"><p>No notifications.</p></div> : null}
        </div>
      </section>
    </div>
  );
}

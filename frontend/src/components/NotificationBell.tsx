import React, { useEffect, useState, useRef } from "react";
import { fetchNotifications, markAllNotificationsRead } from "../api";
import type { NotificationItem } from "../types";

export default function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    async function poll() {
      try {
        const unread = await fetchNotifications(true, 1000);
        if (!mounted.current) return;
        setUnreadCount(unread.length || 0);
      } catch (e) {
        // ignore
      }
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    (async () => {
      try {
        const recent = await fetchNotifications(false, 10);
        if (!alive) return;
        setItems(recent);
      } catch (e) {
        // ignore
      }
    })();
    return () => {
      alive = false;
    };
  }, [open]);

  async function handleMarkAll() {
    try {
      await markAllNotificationsRead();
      setUnreadCount(0);
      const recent = await fetchNotifications(false, 10);
      setItems(recent);
    } catch (e) {
      // ignore
    }
  }

  return (
    <div className="notification-bell" style={{ position: "relative" }}>
      <button className="button ghost-button" onClick={() => setOpen((v) => !v)} aria-label="Notifications">
        🔔
        {unreadCount > 0 && (
          <span className="badge" style={{ marginLeft: 6 }}>{unreadCount}</span>
        )}
      </button>
      {open && (
        <div className="notification-dropdown panel" style={{ position: "absolute", right: 0, top: "40px", width: 360, zIndex: 40 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <strong>Notifications</strong>
            <button className="button ghost-button" onClick={handleMarkAll}>Mark all read</button>
          </div>
          <div style={{ maxHeight: 320, overflowY: "auto" }}>
            {items.length === 0 && <div className="muted">No notifications</div>}
            {items.map((n) => (
              <div key={n.id} style={{ padding: "8px 4px", borderBottom: "1px solid #eee" }}>
                <div style={{ fontSize: 13 }}>{n.message}</div>
                <div className="muted" style={{ fontSize: 12 }}>{new Date(n.created_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

type Props = {
  unread: number;
  onOpen: () => void;
};

export function NotificationBellRetail({ unread, onOpen }: Props) {
  return (
    <button type="button" className="retail-icon-btn notif-bell" onClick={onOpen} aria-label={`Notifications ${unread} unread`}>
      <span aria-hidden>🔔</span>
      {unread > 0 ? <span className="notif-badge">{unread > 99 ? "99+" : unread}</span> : null}
    </button>
  );
}

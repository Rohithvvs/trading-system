import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastLevel = "success" | "error" | "warning" | "info" | "loading";

export type ToastItem = {
  id: string;
  level: ToastLevel;
  message: string;
  description?: string;
  duration?: number;
  /** Dedup key — identical keys replace existing toast instead of stacking */
  dedupeKey?: string;
};

type ToastInput = Partial<Omit<ToastItem, "id" | "message">> & { message: string };

type ToastContextValue = {
  toasts: ToastItem[];
  toast: (message: string, opts?: Partial<Omit<ToastItem, "id" | "message">>) => string;
  success: (message: string, description?: string) => string;
  error: (message: string, description?: string) => string;
  warning: (message: string, description?: string) => string;
  info: (message: string, description?: string) => string;
  loading: (message: string, description?: string) => string;
  dismiss: (id: string) => void;
  dismissAll: () => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const MAX_VISIBLE = 3;
let toastSeq = 0;

/** Flag so non-React helpers know a managed toast host is alive */
function setToastHostReady(ready: boolean) {
  try {
    (window as any).__TRADEDESK_TOAST_READY__ = ready;
  } catch {
    /* ignore */
  }
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const queueRef = useRef<ToastItem[]>([]);
  const timers = useRef<Map<string, number>>(new Map());
  const visibleRef = useRef<ToastItem[]>([]);

  useEffect(() => {
    visibleRef.current = toasts;
  }, [toasts]);

  useEffect(() => {
    setToastHostReady(true);
    return () => setToastHostReady(false);
  }, []);

  const clearTimer = useCallback((id: string) => {
    const t = timers.current.get(id);
    if (t) {
      window.clearTimeout(t);
      timers.current.delete(id);
    }
  }, []);

  const scheduleDismiss = useCallback(
    (item: ToastItem) => {
      clearTimer(item.id);
      const duration = item.duration ?? 0;
      if (duration > 0) {
        const handle = window.setTimeout(() => {
          dismissInternal(item.id);
        }, duration);
        timers.current.set(item.id, handle);
      }
    },
    [clearTimer],
  );

  const promoteFromQueue = useCallback(() => {
    setToasts((prev) => {
      if (prev.length >= MAX_VISIBLE) return prev;
      const next = [...prev];
      while (next.length < MAX_VISIBLE && queueRef.current.length > 0) {
        const item = queueRef.current.shift()!;
        next.push(item);
        scheduleDismiss(item);
      }
      return next;
    });
  }, [scheduleDismiss]);

  const dismissInternal = useCallback(
    (id: string) => {
      clearTimer(id);
      setToasts((prev) => {
        const next = prev.filter((t) => t.id !== id);
        return next;
      });
      // Promote queued items on next tick after state flush
      window.setTimeout(() => promoteFromQueue(), 0);
    },
    [clearTimer, promoteFromQueue],
  );

  const dismiss = useCallback(
    (id: string) => {
      dismissInternal(id);
    },
    [dismissInternal],
  );

  const dismissAll = useCallback(() => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current.clear();
    queueRef.current = [];
    setToasts([]);
  }, []);

  const toast = useCallback(
    (message: string, opts?: Partial<Omit<ToastItem, "id" | "message">>) => {
      const level = opts?.level ?? "info";
      const duration =
        opts?.duration ?? (level === "loading" ? 0 : level === "error" ? 6000 : level === "warning" ? 5000 : 4000);
      const dedupeKey = opts?.dedupeKey ?? `${level}:${message}:${opts?.description ?? ""}`;

      // Deduplicate: replace existing visible or queued with same key
      const existingVisible = visibleRef.current.find((t) => t.dedupeKey === dedupeKey);
      if (existingVisible) {
        clearTimer(existingVisible.id);
        const updated: ToastItem = {
          ...existingVisible,
          message,
          description: opts?.description,
          level,
          duration,
        };
        setToasts((prev) => prev.map((t) => (t.id === existingVisible.id ? updated : t)));
        scheduleDismiss(updated);
        return existingVisible.id;
      }

      const queuedIdx = queueRef.current.findIndex((t) => t.dedupeKey === dedupeKey);
      if (queuedIdx >= 0) {
        const id = queueRef.current[queuedIdx].id;
        queueRef.current[queuedIdx] = {
          ...queueRef.current[queuedIdx],
          message,
          description: opts?.description,
          level,
          duration,
        };
        return id;
      }

      const id = `toast-${++toastSeq}-${Date.now()}`;
      const item: ToastItem = {
        id,
        message,
        level,
        description: opts?.description,
        duration,
        dedupeKey,
      };

      setToasts((prev) => {
        if (prev.length < MAX_VISIBLE) {
          scheduleDismiss(item);
          return [...prev, item];
        }
        // Queue when full
        queueRef.current.push(item);
        // Cap queue
        if (queueRef.current.length > 10) queueRef.current = queueRef.current.slice(-10);
        return prev;
      });

      return id;
    },
    [clearTimer, scheduleDismiss],
  );

  const api = useMemo<ToastContextValue>(
    () => ({
      toasts,
      toast,
      success: (m, d) => toast(m, { level: "success", description: d }),
      error: (m, d) => toast(m, { level: "error", description: d }),
      warning: (m, d) => toast(m, { level: "warning", description: d }),
      info: (m, d) => toast(m, { level: "info", description: d }),
      loading: (m, d) => toast(m, { level: "loading", description: d, duration: 0 }),
      dismiss,
      dismissAll,
    }),
    [toasts, toast, dismiss, dismissAll],
  );

  // Single global bridge — only ToastProvider renders toasts
  useEffect(() => {
    const handler = (ev: Event) => {
      const detail = (ev as CustomEvent).detail || {};
      const level = (detail.level as ToastLevel) || "info";
      toast(detail.message || "Notification", {
        level,
        description: detail.description,
        duration: detail.duration,
        dedupeKey: detail.dedupeKey,
      });
    };
    window.addEventListener("app:toast", handler as EventListener);
    return () => window.removeEventListener("app:toast", handler as EventListener);
  }, [toast]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} queueCount={queueRef.current.length} />
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return {
      toasts: [],
      toast: (m) => {
        // No host — dispatch event so a late-mounted provider can catch if any
        try {
          window.dispatchEvent(
            new CustomEvent("app:toast", { detail: { level: "info", message: m } }),
          );
        } catch {
          console.info("[toast]", m);
        }
        return "";
      },
      success: (m, d) => {
        window.dispatchEvent(
          new CustomEvent("app:toast", { detail: { level: "success", message: m, description: d } }),
        );
        return "";
      },
      error: (m, d) => {
        window.dispatchEvent(
          new CustomEvent("app:toast", { detail: { level: "error", message: m, description: d } }),
        );
        return "";
      },
      warning: (m, d) => {
        window.dispatchEvent(
          new CustomEvent("app:toast", { detail: { level: "warning", message: m, description: d } }),
        );
        return "";
      },
      info: (m, d) => {
        window.dispatchEvent(
          new CustomEvent("app:toast", { detail: { level: "info", message: m, description: d } }),
        );
        return "";
      },
      loading: (m, d) => {
        window.dispatchEvent(
          new CustomEvent("app:toast", { detail: { level: "loading", message: m, description: d } }),
        );
        return "";
      },
      dismiss: () => undefined,
      dismissAll: () => undefined,
    };
  }
  return ctx;
}

function ToastViewport({
  toasts,
  onDismiss,
  queueCount,
}: {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
  queueCount: number;
}) {
  return (
    <div
      className="ds-toast-viewport"
      aria-live="polite"
      aria-relevant="additions text"
      data-testid="toast-viewport"
    >
      {toasts.map((t, index) => (
        <div
          key={t.id}
          className={`ds-toast ds-toast--${t.level}`}
          role={t.level === "error" || t.level === "warning" ? "alert" : "status"}
          style={{ animationDelay: `${index * 30}ms` }}
        >
          <span className="ds-toast__icon" aria-hidden>
            {iconFor(t.level)}
          </span>
          <div className="ds-toast__body">
            <div className="ds-toast__message">{t.message}</div>
            {t.description ? <div className="ds-toast__desc">{t.description}</div> : null}
          </div>
          {t.level !== "loading" ? (
            <button
              type="button"
              className="ds-toast__close"
              onClick={() => onDismiss(t.id)}
              aria-label="Dismiss notification"
            >
              ×
            </button>
          ) : (
            <span className="ds-toast__spinner" aria-hidden />
          )}
        </div>
      ))}
      {queueCount > 0 ? (
        <div className="ds-toast-queue-hint ds-caption" aria-live="off">
          +{queueCount} more
        </div>
      ) : null}
    </div>
  );
}

function iconFor(level: ToastLevel): string {
  switch (level) {
    case "success":
      return "✓";
    case "error":
      return "!";
    case "warning":
      return "⚠";
    case "loading":
      return "…";
    default:
      return "i";
  }
}

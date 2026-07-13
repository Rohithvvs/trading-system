import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./Button";

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: ReactNode;
  /** Footer actions — if omitted, only close */
  footer?: ReactNode;
  size?: "sm" | "md" | "lg";
};

export function Modal({ open, onClose, title, description, children, footer, size = "md" }: Props) {
  const titleId = useId();
  const descId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="ds-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={`ds-modal ds-modal--${size}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ds-modal__header">
          <h2 id={titleId} className="ds-modal__title">
            {title}
          </h2>
          <button type="button" className="ds-modal__close" onClick={onClose} aria-label="Close dialog">
            ×
          </button>
        </div>
        {description ? (
          <p id={descId} className="ds-modal__desc">
            {description}
          </p>
        ) : null}
        {children ? <div className="ds-modal__body">{children}</div> : null}
        {footer ? <div className="ds-modal__footer">{footer}</div> : null}
      </div>
    </div>
  );
}

type ConfirmProps = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "primary";
  loading?: boolean;
};

/** Destructive / high-impact confirmation dialog */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger",
  loading,
}: ConfirmProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={tone === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}

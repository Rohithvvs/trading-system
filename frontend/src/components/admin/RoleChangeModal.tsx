import { ConfirmDialog } from "../../design-system";
import type { AdminRole, AdminUser } from "../../api_admin";

type Props = {
  open: boolean;
  user: AdminUser | null;
  nextRole: AdminRole | null;
  loading?: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

export function RoleChangeModal({ open, user, nextRole, loading, onClose, onConfirm }: Props) {
  const email = user?.email ?? "this user";
  const roleLabel = nextRole ?? "trader";
  return (
    <ConfirmDialog
      open={open}
      onClose={onClose}
      onConfirm={onConfirm}
      title="Change user role"
      description={`Change ${email} to ${roleLabel}? This updates their privileges immediately.`}
      confirmLabel={nextRole === "admin" ? "Promote to admin" : "Demote to trader"}
      cancelLabel="Cancel"
      tone={nextRole === "trader" ? "danger" : "primary"}
      loading={loading}
    />
  );
}

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "buy" | "sell" | "trade";
export type ButtonSize = "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
};

const variantClass: Record<ButtonVariant, string> = {
  primary: "ds-btn--primary",
  secondary: "ds-btn--secondary",
  ghost: "ds-btn--ghost",
  danger: "ds-btn--danger",
  buy: "ds-btn--buy",
  sell: "ds-btn--sell",
  trade: "ds-btn--trade",
};

const sizeClass: Record<ButtonSize, string> = {
  sm: "ds-btn--sm",
  md: "ds-btn--md",
  lg: "ds-btn--lg",
};

/**
 * Primary CTAs for trading actions should use buy | sell | trade.
 * All other actions use secondary | ghost | danger.
 */
export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  {
    variant = "secondary",
    size = "md",
    fullWidth,
    loading,
    leftIcon,
    rightIcon,
    className = "",
    disabled,
    children,
    type = "button",
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={[
        "ds-btn",
        variantClass[variant],
        sizeClass[size],
        fullWidth ? "ds-btn--full" : "",
        loading ? "ds-btn--loading" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className="ds-btn__spinner" aria-hidden /> : leftIcon}
      <span className="ds-btn__label">{children}</span>
      {!loading ? rightIcon : null}
    </button>
  );
});

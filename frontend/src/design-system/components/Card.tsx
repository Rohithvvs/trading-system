import type { HTMLAttributes, ReactNode } from "react";

type Props = HTMLAttributes<HTMLElement> & {
  as?: "section" | "article" | "div";
  padding?: "none" | "sm" | "md" | "lg";
  elevated?: boolean;
  children: ReactNode;
};

export function Card({
  as: Tag = "section",
  padding = "md",
  elevated,
  className = "",
  children,
  ...rest
}: Props) {
  return (
    <Tag
      className={[
        "ds-card",
        `ds-card--pad-${padding}`,
        elevated ? "ds-card--elevated" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...rest}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({
  label,
  title,
  description,
  actions,
}: {
  label?: string;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="ds-card__header">
      <div className="ds-card__header-text">
        {label ? <p className="ds-label">{label}</p> : null}
        {title ? <h2 className="ds-title">{title}</h2> : null}
        {description ? <p className="ds-muted">{description}</p> : null}
      </div>
      {actions ? <div className="ds-card__actions">{actions}</div> : null}
    </div>
  );
}

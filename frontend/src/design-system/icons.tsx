/** Lightweight inline SVG icons for navigation and sections */
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
    ...rest,
  };
}

export function IconScanner(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
      <path d="M11 8v3h3" />
    </svg>
  );
}

export function IconFilters(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 6h16M7 12h10M10 18h4" />
    </svg>
  );
}

export function IconMarket(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 3v18h18" />
      <path d="M7 14l4-4 3 3 5-6" />
    </svg>
  );
}

export function IconWatchlist(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3l2.4 6.6H21l-5.4 4 2 6.4L12 16.2 6.4 20l2-6.4L3 9.6h6.6z" />
    </svg>
  );
}

export function IconPortfolio(p: IconProps) {
  return (
    <svg {...base(p)}>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

export function IconOrders(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  );
}

export function IconSignals(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  );
}

export function IconAnalytics(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M4 19V5M8 19v-8M12 19v-5M16 19V9M20 19v-3" />
    </svg>
  );
}

export function IconSettings(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function IconProfile(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20a8 8 0 0 1 16 0" />
    </svg>
  );
}

export function IconTrendUp(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M14 7h7v7" />
    </svg>
  );
}

export function IconRisk(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M12 3l9 16H3L12 3z" />
      <path d="M12 10v4M12 17h.01" />
    </svg>
  );
}

export function IconSearch(p: IconProps) {
  return (
    <svg {...base(p)}>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" />
    </svg>
  );
}

export function IconSave(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
      <path d="M17 21v-8H7v8M7 3v5h8" />
    </svg>
  );
}

export function IconReset(p: IconProps) {
  return (
    <svg {...base(p)}>
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
    </svg>
  );
}

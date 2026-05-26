import { useInfrastructureHealth, type ServiceBadgeState } from "../hooks/useInfrastructureHealth";

export function InfrastructureStatus() {
  const { renderStatus, databaseStatus, latencyMs, infraState, lastCheckedAt, error } = useInfrastructureHealth();
  const title = [
    `Infrastructure: ${infraState}`,
    latencyMs === null ? "Latency unavailable" : `Latency: ${latencyMs}ms`,
    lastCheckedAt ? `Last checked: ${lastCheckedAt.toLocaleTimeString()}` : null,
    error,
  ]
    .filter(Boolean)
    .join(" | ");

  return (
    <div
      className="flex min-w-[260px] flex-col gap-1 rounded-lg border border-slate-700/70 bg-slate-950/40 px-3 py-2 text-xs text-slate-200 shadow-sm"
      title={title}
      aria-label="Infrastructure health"
    >
      <InfrastructureRow label="Render Server" status={renderStatus} />
      <InfrastructureRow label="Neon Database" status={databaseStatus} />
    </div>
  );
}

function InfrastructureRow({ label, status }: { label: string; status: ServiceBadgeState }) {
  const badge = getBadge(status);

  return (
    <div className="flex items-center justify-between gap-3">
      <span className="whitespace-nowrap font-medium text-slate-300">{label}</span>
      <span className="inline-flex min-w-[104px] items-center gap-2 rounded-full border border-slate-700/80 bg-slate-900/80 px-2.5 py-1 font-semibold text-slate-100">
        <span className={`h-2 w-2 rounded-full ${badge.dotClass}`} aria-hidden="true" />
        {badge.text}
      </span>
    </div>
  );
}

function getBadge(status: ServiceBadgeState) {
  if (status === "active") {
    return {
      text: "Active",
      dotClass: "bg-green-500",
    };
  }

  if (status === "waking") {
    return {
      text: "Waking Up...",
      dotClass: "bg-yellow-500 animate-pulse",
    };
  }

  return {
    text: "Asleep",
    dotClass: "bg-red-500",
  };
}

import { useInfrastructureHealth, type ServiceBadgeState } from "../hooks/useInfrastructureHealth";

const BADGE_CONFIG: Record<ServiceBadgeState, { text: string; dotClass: string }> = {
  active: { text: "Active", dotClass: "infra-card__dot--active" },
  waking: { text: "Waking Up", dotClass: "infra-card__dot--waking" },
  connecting: { text: "Connecting", dotClass: "infra-card__dot--connecting" },
  offline: { text: "Offline", dotClass: "infra-card__dot--offline" },
  sleeping: { text: "Sleeping", dotClass: "infra-card__dot--sleeping" },
};

export function InfrastructureStatus() {
  const { services, lastCheckedAt, error } = useInfrastructureHealth();

  return (
    <div className="infra-panel" aria-label="Infrastructure health">
      <h3 className="infra-panel__header">
        Infrastructure
        {lastCheckedAt && (
          <span className="infra-panel__time">
            · {lastCheckedAt.toLocaleTimeString()}
          </span>
        )}
      </h3>
      <div className="infra-cards">
        {services.map((svc) => {
          const badge = BADGE_CONFIG[svc.status] || BADGE_CONFIG.sleeping;
          return (
            <div key={svc.key} className="infra-card" data-status={svc.status}>
              <div className="infra-card__row">
                <span className={`infra-card__dot ${badge.dotClass}`} aria-hidden />
                <span className="infra-card__label">{svc.label}</span>
              </div>
              <span className="infra-card__badge">
                {badge.text}
                {svc.meta && <span className="infra-card__meta">{svc.meta}</span>}
              </span>
            </div>
          );
        })}
      </div>
      {error && <p className="infra-panel__error">{error}</p>}
    </div>
  );
}

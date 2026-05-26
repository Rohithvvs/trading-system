import { useEffect, useState } from "react";

export type InfrastructureState = "Active" | "DB Waking" | "Server Waking" | "Asleep";
export type ServiceBadgeState = "active" | "waking" | "asleep";

type InfrastructureHealth = {
  latencyMs: number | null;
  infraState: InfrastructureState;
  renderStatus: ServiceBadgeState;
  databaseStatus: ServiceBadgeState;
  lastCheckedAt: Date | null;
  error: string | null;
};

const POLL_INTERVAL_MS = 15_000;
const REQUEST_TIMEOUT_MS = 10_000;
const ACTIVE_THRESHOLD_MS = 1_500;
const DB_WAKE_THRESHOLD_MS = 4_000;

const initialHealth: InfrastructureHealth = {
  latencyMs: null,
  infraState: "Asleep",
  renderStatus: "asleep",
  databaseStatus: "asleep",
  lastCheckedAt: null,
  error: null,
};

export function useInfrastructureHealth() {
  const [health, setHealth] = useState<InfrastructureHealth>(initialHealth);

  useEffect(() => {
    let isMounted = true;
    let isPolling = false;
    let activeController: AbortController | null = null;

    const baseUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
    const healthPath = import.meta.env.VITE_INFRA_HEALTH_PATH || "/paper-trading/engine/status";
    const endpoint = `${baseUrl}${healthPath}`;

    async function pingHealth() {
      if (isPolling) return;

      isPolling = true;
      activeController = new AbortController();
      const timeoutId = window.setTimeout(() => activeController?.abort(), REQUEST_TIMEOUT_MS);
      const startedAt = performance.now();

      try {
        const response = await fetch(endpoint, {
          method: "GET",
          headers: { "Cache-Control": "no-cache" },
          signal: activeController.signal,
        });

        const latencyMs = Math.round(performance.now() - startedAt);
        if (!isMounted) return;

        if (!response.ok) {
          setHealth({
            ...initialHealth,
            lastCheckedAt: new Date(),
            error: `Health check returned HTTP ${response.status}`,
          });
          return;
        }

        setHealth({
          latencyMs,
          ...mapLatencyToHealth(latencyMs),
          lastCheckedAt: new Date(),
          error: null,
        });
      } catch (error) {
        if (!isMounted) return;

        setHealth({
          ...initialHealth,
          lastCheckedAt: new Date(),
          error: error instanceof Error ? error.message : "Health check failed",
        });
      } finally {
        window.clearTimeout(timeoutId);
        activeController = null;
        isPolling = false;
      }
    }

    void pingHealth();
    const intervalId = window.setInterval(() => void pingHealth(), POLL_INTERVAL_MS);

    return () => {
      isMounted = false;
      activeController?.abort();
      window.clearInterval(intervalId);
    };
  }, []);

  return health;
}

function mapLatencyToHealth(latencyMs: number): Pick<InfrastructureHealth, "infraState" | "renderStatus" | "databaseStatus"> {
  if (latencyMs < ACTIVE_THRESHOLD_MS) {
    return {
      infraState: "Active",
      renderStatus: "active",
      databaseStatus: "active",
    };
  }

  if (latencyMs <= DB_WAKE_THRESHOLD_MS) {
    return {
      infraState: "DB Waking",
      renderStatus: "active",
      databaseStatus: "waking",
    };
  }

  return {
    infraState: "Server Waking",
    renderStatus: "waking",
    databaseStatus: "waking",
  };
}

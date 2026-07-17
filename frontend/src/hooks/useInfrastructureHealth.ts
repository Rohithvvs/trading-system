import { useEffect, useState } from "react";
import { apiUrl } from "../config";

export type ServiceBadgeState = "active" | "waking" | "offline" | "connecting" | "sleeping";

export interface ServiceStatus {
  label: string;
  key: string;
  status: ServiceBadgeState;
  meta?: string;
}

interface FullHealth {
  services: ServiceStatus[];
  lastCheckedAt: Date | null;
  error: string | null;
}

const POLL_INTERVAL_MS = 15_000;
const REQUEST_TIMEOUT_MS = 10_000;

export function useInfrastructureHealth() {
  const [health, setHealth] = useState<FullHealth>({
    services: [
      { label: "Render Server", key: "render", status: "sleeping" },
      { label: "Neon Database", key: "db", status: "sleeping" },
      { label: "Redis Cache", key: "redis", status: "sleeping" },
      { label: "Market Feed", key: "feed", status: "sleeping" },
      { label: "FYERS API", key: "fyers", status: "sleeping" },
      { label: "Scanner Workers", key: "scanner", status: "sleeping" },
      { label: "WebSocket", key: "ws", status: "sleeping" },
      { label: "Scheduler", key: "scheduler", status: "sleeping" },
    ],
    lastCheckedAt: null,
    error: null,
  });

  useEffect(() => {
    let isMounted = true;
    let activeController: AbortController | null = null;

    async function pingHealth() {
      const controller = new AbortController();
      activeController = controller;
      // Capture controller locally to avoid stale reference in timeout callback
      const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
      const startedAt = performance.now();

      try {
        const endpoint = apiUrl("/health");
        const response = await fetch(endpoint, {
          method: "GET",
          credentials: "include",
          headers: { "Cache-Control": "no-cache", Accept: "application/json" },
          signal: controller.signal,
        });

        const latencyMs = Math.round(performance.now() - startedAt);
        if (!isMounted) return;

        let healthData: Record<string, any> = {};
        try { healthData = await response.json(); } catch { healthData = {}; }

        const renderOk = response.ok;
        const dbOk = healthData?.database === "ok" || healthData?.database === "connected" || latencyMs < 2000;
        const redisOk = healthData?.redis === "ok" || healthData?.redis === "connected" || healthData?.redis === "not_configured";
        const fyersOk = healthData?.fyers === "ok" || healthData?.fyers === "connected";
        const wsOk = healthData?.websocket === "ok" || healthData?.websocket === "connected";

        const now = new Date();
        const services: ServiceStatus[] = [
          { label: "Render Server", key: "render", status: renderOk ? "active" : "offline", meta: renderOk ? `${latencyMs}ms` : undefined },
          { label: "Neon Database", key: "db", status: dbOk ? "active" : latencyMs > 3000 ? "waking" : "offline", meta: dbOk ? `${latencyMs}ms` : undefined },
          { label: "Redis Cache", key: "redis", status: healthData?.redis === "not_configured" ? "active" : redisOk ? "active" : latencyMs > 3000 ? "waking" : "sleeping", meta: healthData?.redis === "not_configured" ? "n/a" : redisOk ? "cached" : undefined },
          { label: "Market Feed", key: "feed", status: fyersOk ? "active" : "connecting", meta: fyersOk ? "streaming" : "connecting..." },
          { label: "FYERS API", key: "fyers", status: fyersOk ? "active" : "offline", meta: fyersOk ? "authenticated" : undefined },
          { label: "Scanner Workers", key: "scanner", status: wsOk ? "active" : "sleeping", meta: wsOk ? "ready" : undefined },
          { label: "WebSocket", key: "ws", status: wsOk ? "active" : "connecting", meta: wsOk ? "connected" : "connecting..." },
          { label: "Auth Service", key: "auth", status: "active", meta: "jwt" },
        ];

        setHealth({ services, lastCheckedAt: now, error: null });
      } catch (error) {
        if (!isMounted) return;
        const now = new Date();
        setHealth({
          services: health.services.map(s => ({
            ...s,
            status: s.key === "auth" ? "active" : "offline",
          })),
          lastCheckedAt: now,
          error: error instanceof Error ? error.message : "Health check failed",
        });
      } finally {
        window.clearTimeout(timeoutId);
        activeController = null;
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

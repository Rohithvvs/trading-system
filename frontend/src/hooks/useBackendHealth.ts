import { useEffect, useState } from "react";
import { checkBackendHealth } from "../api";

export type BackendHealthStatus = "checking" | "ok" | "down";

/**
 * Probes GET /health for ops badges and network-dependent UI.
 */
export function useBackendHealth() {
  const [status, setStatus] = useState<BackendHealthStatus>("checking");
  const [message, setMessage] = useState("Checking server connection…");
  const [url, setUrl] = useState("");

  useEffect(() => {
    let cancelled = false;
    void checkBackendHealth().then((result) => {
      if (cancelled) return;
      setUrl(result.url);
      if (result.ok) {
        setStatus("ok");
        setMessage(`Server reachable (${result.latencyMs}ms)`);
      } else {
        setStatus("down");
        // Prefer stable user-facing copy over raw transport noise.
        setMessage(result.message || "Cannot connect to server.");
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { status, message, url, isReady: status === "ok", isDown: status === "down" };
}

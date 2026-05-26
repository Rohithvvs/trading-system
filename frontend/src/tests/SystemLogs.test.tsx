import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SystemLogs } from "../pages/SystemLogs";

class StableMockWebSocket {
  static instances: StableMockWebSocket[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  readyState = 0;
  url: string;

  constructor(url: string) {
    this.url = url;
    StableMockWebSocket.instances.push(this);
    window.setTimeout(() => {
      this.readyState = 1;
      this.onopen?.(new Event("open"));
    }, 0);
  }

  close() {
    this.readyState = 3;
  }

  send() {}
}

describe("SystemLogs", () => {
  beforeEach(() => {
    StableMockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", StableMockWebSocket);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => [
          {
            id: 1,
            timestamp: "2026-05-25T08:00:00Z",
            level: "CRITICAL",
            source: "SYSTEM",
            module: "RiskEngine",
            message: "circuit open",
            structured_data: {},
          },
          {
            id: 2,
            timestamp: "2026-05-25T08:01:00Z",
            level: "WARN",
            source: "JOB",
            module: "Scheduler",
            message: "late candle",
            structured_data: {},
          },
          {
            id: 3,
            timestamp: "2026-05-25T08:02:00Z",
            level: "INFO",
            source: "API",
            module: "Health",
            message: "ok",
            structured_data: {},
          },
        ],
      })),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders level-specific terminal color classes", async () => {
    const { container } = render(<SystemLogs />);

    await waitFor(() => expect(screen.getByText("circuit open")).toBeDefined());

    expect(container.querySelector(".log-level.text-red-500")?.textContent).toBe("CRITICAL");
    expect(container.querySelector(".log-level.text-yellow-500")?.textContent).toBe("WARN");
    expect(container.querySelector(".log-level.text-green-500")?.textContent).toBe("INFO");
  });
});

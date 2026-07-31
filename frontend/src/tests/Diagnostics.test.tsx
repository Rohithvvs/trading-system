import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DiagnosticsPage } from "../pages/Diagnostics";
import { ThemeProvider } from "../hooks/useTheme";

function renderDiagnosticsPage() {
  return render(
    <ThemeProvider>
      <DiagnosticsPage />
    </ThemeProvider>
  );
}

function mockFetch(handlers: Record<string, (url: string) => unknown>) {
  return vi.fn(async (url: string) => {
    for (const [pattern, handler] of Object.entries(handlers)) {
      if (url.includes(pattern)) {
        return {
          ok: true,
          status: 200,
          json: async () => handler(url),
        };
      }
    }
    return { ok: false, status: 404, json: async () => ({}) };
  });
}

const DEFAULT_HANDLERS = {
  "/api/v1/dashboard/metrics": () => ({
    system: {
      cpu_percent: 45.2,
      memory_percent: 62.1,
      memory_used_mb: 1024,
      request_rate_per_sec: 15.3,
      error_rate_per_sec: 0.1,
    },
  }),
  "/api/v1/dashboard/logs": () => ({
    entries: [
      {
        timestamp: "2026-07-16T10:00:00Z",
        level: "info",
        source: "governance.experiment",
        message: "Experiment started",
        metadata: { experiment_id: "uuid" },
      },
    ],
    total: 1,
    limit: 100,
    offset: 0,
  }),
  "/api/v1/dashboard/alerts": () => ({
    alerts: [
      {
        uuid: "alert-1",
        rule_name: "high-cpu",
        severity: "warning",
        metric_name: "cpu_percent",
        metric_value: 85.0,
        threshold: 80.0,
        message: "CPU exceeded 80%",
        timestamp: "2026-07-16T10:01:00Z",
      },
    ],
  }),
};

describe("Diagnostics Page", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", mockFetch(DEFAULT_HANDLERS));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders the page title 'Diagnostics Dashboard'", async () => {
    renderDiagnosticsPage();
    expect(screen.getByText("Diagnostics Dashboard")).toBeDefined();
  });

  it("renders all four diagnostic panels", async () => {
    renderDiagnosticsPage();
    await waitFor(() => {
      expect(screen.getByText("System Metrics")).toBeDefined();
      expect(screen.getByText("Log Viewer")).toBeDefined();
      expect(screen.getByText("Active Alerts")).toBeDefined();
      expect(screen.getByText("Experiment Resource Usage")).toBeDefined();
    });
  });

  it("System Metrics panel displays CPU and Memory values", async () => {
    renderDiagnosticsPage();
    await waitFor(() => {
      expect(screen.getByText("System Metrics")).toBeDefined();
      // The mock returns cpu_percent=45.2 and memory_percent=62.1
      expect(screen.getByText("45.2%")).toBeDefined();
      expect(screen.getByText("62.1%")).toBeDefined();
    });
  });

  it("Log Viewer panel displays ingested log entries", async () => {
    renderDiagnosticsPage();
    await waitFor(() => {
      expect(screen.getByText("Experiment started")).toBeDefined();
    });
  });

  it("Alerts panel displays active alerts with severity badge", async () => {
    renderDiagnosticsPage();
    await waitFor(() => {
      expect(screen.getByText("high-cpu")).toBeDefined();
      expect(screen.getByText("CPU exceeded 80%")).toBeDefined();
    });
  });

  it("Resource Usage panel shows 'No active experiment' when none active", async () => {
    renderDiagnosticsPage();
    await waitFor(() => {
      expect(screen.getByText("No active experiment.")).toBeDefined();
    });
  });

  it("LogViewer level filter dropdown is present", async () => {
    const { container } = render(<DiagnosticsPage />);
    await waitFor(() => {
      const select = container.querySelector("select");
      expect(select).toBeDefined();
    });
  });
});

describe("Diagnostics Page — Error State", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("Backend unreachable");
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows error and Retry button when backend is unreachable", async () => {
    renderDiagnosticsPage();
    await waitFor(() => {
      expect(screen.getAllByText("Backend unreachable")[0]).toBeDefined();
    });

    // MetricsPanel should have a Retry button
    const retryButtons = screen.getAllByText("Retry");
    expect(retryButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("retried when Retry button clicked", async () => {
    const mockFn = vi.fn(async () => {
      throw new Error("Backend unreachable");
    });
    vi.stubGlobal("fetch", mockFn);

    render(
      <ThemeProvider>
        <DiagnosticsPage />
      </ThemeProvider>
    );
    await waitFor(() => {
      expect(screen.getAllByText("Backend unreachable")[0]).toBeDefined();
    });

    const retryButtons = screen.getAllByText("Retry");
    fireEvent.click(retryButtons[0]);

    // fetch should have been called more times (at least once more from click)
    await waitFor(() => {
      expect(mockFn.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });
});

describe("Diagnostics Page — Empty State", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      mockFetch({
        "/api/v1/dashboard/metrics": () => ({
          system: {
            cpu_percent: 0,
            memory_percent: 0,
            memory_used_mb: 0,
            request_rate_per_sec: 0,
            error_rate_per_sec: 0,
          },
        }),
        "/api/v1/dashboard/logs": () => ({
          entries: [],
          total: 0,
          limit: 100,
          offset: 0,
        }),
        "/api/v1/dashboard/alerts": () => ({ alerts: [] }),
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("Alerts panel shows 'No active alerts' when empty", async () => {
    renderDiagnosticsPage();
    await waitFor(() => {
      expect(screen.getByText("No active alerts.")).toBeDefined();
    });
  });

  it("LogViewer shows 'No log entries found' when empty", async () => {
    renderDiagnosticsPage();
    await waitFor(() => {
      expect(screen.getByText("No log entries found.")).toBeDefined();
    });
  });
});
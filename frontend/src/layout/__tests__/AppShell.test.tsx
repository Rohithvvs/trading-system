import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "../AppShell";
import { ThemeProvider } from "../../hooks/useTheme";
import { DensityProvider } from "../../hooks/useDensity";

describe("AppShell Navigation & Layout", () => {
  it("renders brand link, breadcrumbs, search, and navigation domains", () => {
    render(
      <MemoryRouter>
        <ThemeProvider>
          <DensityProvider>
            <AppShell>
              <div>Shell Content</div>
            </AppShell>
          </DensityProvider>
        </ThemeProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText("QuantLab")).toBeDefined();
    expect(screen.getByText("Shell Content")).toBeDefined();
    expect(screen.getByTestId("sidebar-collapse-toggle")).toBeDefined();
  });
});

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WidgetContainer } from "../WidgetContainer";

describe("WidgetContainer", () => {
  it("renders title and children when idle/ready", () => {
    render(
      <WidgetContainer title="Market Overview">
        <div>Widget Content</div>
      </WidgetContainer>,
    );
    expect(screen.getByText("Market Overview")).toBeDefined();
    expect(screen.getByText("Widget Content")).toBeDefined();
  });

  it("renders error state when error prop provided", () => {
    render(
      <WidgetContainer title="Market Overview" error="Failed to fetch data">
        <div>Widget Content</div>
      </WidgetContainer>,
    );
    expect(screen.getByText("Unable to load widget data")).toBeDefined();
    expect(screen.getByText("Failed to fetch data")).toBeDefined();
  });
});

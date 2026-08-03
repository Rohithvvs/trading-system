import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Re001DetailSection } from "../Re001DetailSection";

describe("Re001DetailSection", () => {
  it("shows empty lab state when no decision", () => {
    render(<Re001DetailSection decision={null} />);
    expect(screen.getByTestId("re001-detail-empty")).toBeTruthy();
    expect(screen.getByText(/No RE-001 lab decision/i)).toBeTruthy();
  });

  it("renders decision fields when present", () => {
    render(
      <Re001DetailSection
        decision={{
          recommendation_id: "abc",
          engine_id: "RE-001",
          engine_version: "1.0",
          recommendation_state: "WATCH",
          confidence_score: 0.66,
          strategy_name: "Trend Following",
          production_action: "BUY",
          explanation: "test evidence",
          reason_codes: ["sideways_strict_pullback"],
        }}
      />,
    );
    expect(screen.getByTestId("re001-detail")).toBeTruthy();
    // State and "vs Production" both include WATCH
    expect(screen.getAllByText(/WATCH/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Trend Following/)).toBeTruthy();
    expect(screen.getByText(/test evidence/)).toBeTruthy();
  });
});

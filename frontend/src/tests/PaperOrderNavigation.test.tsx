import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { navigateToPaperOrder } from "../utils/paperOrderNavigation";

describe("PaperOrderNavigation Utility", () => {
  it("builds query params correctly for paper order ticket", () => {
    let targetPath = "";
    const mockNavigate = (path: string) => {
      targetPath = path;
    };

    navigateToPaperOrder(mockNavigate, {
      symbol: "INFY",
      side: "BUY",
      returnTo: "/research/scanner",
    });

    expect(targetPath).toContain("/paper-order?symbol=INFY");
    expect(targetPath).toContain("side=BUY");
  });
});

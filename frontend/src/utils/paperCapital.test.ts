import { describe, expect, it } from "vitest";
import {
  extractPaperAvailableCash,
  extractPaperMaxRiskPerTrade,
  unwrapPaperAccount,
} from "./paperCapital";

describe("paperCapital", () => {
  it("reads available_cash as primary source of truth", () => {
    expect(
      extractPaperAvailableCash({
        available_cash: 1_000_000,
        available_funds: 0,
        balance: 500,
      }),
    ).toBe(1_000_000);
  });

  it("falls back to available_funds when available_cash is missing (legacy summary)", () => {
    expect(
      extractPaperAvailableCash({
        available_funds: 1_000_000,
        total_capital: 1_000_000,
      }),
    ).toBe(1_000_000);
  });

  it("falls back to balance / cash_balance", () => {
    expect(extractPaperAvailableCash({ balance: 250_000 })).toBe(250_000);
    expect(extractPaperAvailableCash({ cash_balance: 100_000 })).toBe(100_000);
  });

  it("does not treat missing capital as zero", () => {
    expect(extractPaperAvailableCash({})).toBeNull();
    expect(extractPaperAvailableCash(null)).toBeNull();
    expect(extractPaperAvailableCash(undefined)).toBeNull();
  });

  it("unwraps nested dashboard.account payloads", () => {
    const nested = {
      account: { available_cash: 999_999, max_risk_per_trade: 0.03 },
    };
    expect(unwrapPaperAccount(nested)).toEqual(nested.account);
    expect(extractPaperAvailableCash(nested)).toBe(999_999);
    expect(extractPaperMaxRiskPerTrade(nested)).toBe(0.03);
  });

  it("defaults max risk when absent", () => {
    expect(extractPaperMaxRiskPerTrade({})).toBe(0.02);
  });
});

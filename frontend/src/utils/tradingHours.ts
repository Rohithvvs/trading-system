/**
 * Client-side Trading Hours utilities (mirrors backend TradingHoursService).
 *
 * Orders can be placed 24x7. When the market is closed the backend accepts the
 * order with status PENDING_MARKET_OPEN and executes at the next session open.
 * These helpers are for UX messaging only — the backend is authoritative.
 */

export type MarketSessionStatus =
  | "OPEN"
  | "PRE_OPEN"
  | "CLOSED"
  | "WEEKEND"
  | "HOLIDAY";

export interface MarketCheckResult {
  isOpen: boolean;
  status: MarketSessionStatus;
  reason: MarketSessionStatus;
  message: string;
  nextOpenHint: string;
}

const MARKET_OPEN_MINUTES = 9 * 60 + 15; // 09:15 IST
const MARKET_CLOSE_MINUTES = 15 * 60 + 30; // 15:30 IST

// Keep in sync with backend/data/nse_trading_holidays.json
const KNOWN_HOLIDAYS: Record<string, string[]> = {
  "2025": [
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-08-15", "2025-08-27",
    "2025-10-02", "2025-10-20", "2025-10-21", "2025-11-05", "2025-12-25",
  ],
  "2026": [
    "2026-01-26", "2026-02-17", "2026-03-03", "2026-03-20", "2026-04-02",
    "2026-04-03", "2026-04-06", "2026-04-14", "2026-05-01", "2026-08-15",
    "2026-08-28", "2026-10-02", "2026-10-19", "2026-10-20", "2026-11-11", "2026-12-25",
  ],
  "2027": [
    "2027-01-26", "2027-02-26", "2027-03-12", "2027-03-29", "2027-04-02",
    "2027-04-14", "2027-04-26", "2027-05-01", "2027-08-15", "2027-08-17",
    "2027-10-02", "2027-10-08", "2027-10-19", "2027-11-05", "2027-12-25",
  ],
};

function getISTDateParts(d: Date = new Date()) {
  const istFormatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = istFormatter.formatToParts(d);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";

  const year = get("year");
  const month = get("month");
  const day = get("day");
  const hour = parseInt(get("hour"), 10);
  const minute = parseInt(get("minute"), 10);
  const weekday = get("weekday");

  const dateStr = `${year}-${month}-${day}`;
  const minutesSinceMidnight = hour * 60 + minute;
  const isWeekend = weekday === "Sat" || weekday === "Sun";

  return { dateStr, year, minutesSinceMidnight, isWeekend };
}

function isKnownHoliday(dateStr: string, year: string): boolean {
  const list = KNOWN_HOLIDAYS[year] || [];
  return list.includes(dateStr);
}

/** Whether NSE cash market is currently open (client clock / IST). */
export function isMarketOpen(now: Date = new Date()): boolean {
  return getMarketSession(now).isOpen;
}

export function getMarketSession(now: Date = new Date()): MarketCheckResult {
  const { dateStr, year, minutesSinceMidnight, isWeekend } = getISTDateParts(now);

  if (isWeekend) {
    return {
      isOpen: false,
      status: "WEEKEND",
      reason: "WEEKEND",
      message:
        "The market is currently closed (weekend). Your order will be accepted and executed automatically at the next market open.",
      nextOpenHint: "Next Market Open",
    };
  }

  if (isKnownHoliday(dateStr, year)) {
    return {
      isOpen: false,
      status: "HOLIDAY",
      reason: "HOLIDAY",
      message:
        "Today is an official market holiday. Your order will be accepted and executed automatically at the next trading session.",
      nextOpenHint: "Next Market Open",
    };
  }

  if (minutesSinceMidnight < MARKET_OPEN_MINUTES) {
    return {
      isOpen: false,
      status: "PRE_OPEN",
      reason: "PRE_OPEN",
      message:
        "Market has not opened yet (opens 9:15 AM IST). Your order will be accepted and executed when the market opens.",
      nextOpenHint: "Today 9:15 AM IST",
    };
  }

  if (minutesSinceMidnight > MARKET_CLOSE_MINUTES) {
    return {
      isOpen: false,
      status: "CLOSED",
      reason: "CLOSED",
      message:
        "The market is currently closed. Your order will be placed successfully and executed automatically when the market opens.",
      nextOpenHint: "Next Market Open",
    };
  }

  return {
    isOpen: true,
    status: "OPEN",
    reason: "OPEN",
    message: "Market is open. Orders execute immediately when filled.",
    nextOpenHint: "",
  };
}

/** Human-readable order status for the Orders table. */
export function formatOrderStatus(status: string | undefined | null): string {
  switch ((status || "").toUpperCase()) {
    case "PENDING_MARKET_OPEN":
      return "Pending Market Open";
    case "PENDING":
    case "OPEN":
      return "Pending";
    case "PARTIALLY_EXECUTED":
      return "Partially Executed";
    case "FILLED":
    case "EXECUTED":
      return "Executed";
    case "CANCELLED":
      return "Cancelled";
    case "REJECTED":
      return "Rejected";
    default:
      return status || "—";
  }
}

export function isPendingMarketOpen(status: string | undefined | null): boolean {
  return (status || "").toUpperCase() === "PENDING_MARKET_OPEN";
}

export function isOpenOrderStatus(status: string | undefined | null): boolean {
  const s = (status || "").toUpperCase();
  return s === "PENDING" || s === "PENDING_MARKET_OPEN" || s === "OPEN" || s === "PARTIALLY_EXECUTED";
}

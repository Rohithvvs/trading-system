/**
 * Centralized client-side Trading Hours utilities (mirrors backend TradingHoursService).
 *
 * Used for immediate UX blocking of Buy orders so that:
 *   - No API request is sent for orders outside market hours.
 *   - Buttons are disabled.
 *   - Clear alerts shown.
 *
 * NOTE:
 * - Client time may differ from server IST. For final enforcement the backend
 *   TradingHoursService is the source of truth (called inside place_order).
 * - Holidays list should be kept reasonably in sync with backend/data/nse_trading_holidays.json
 * - For production, consider fetching /system/shadow-run/market-status (or dedicated endpoint)
 *   on app boot and using the server answer to override local decision for holidays.
 */

export type MarketBlockReason =
  | "BEFORE_OPEN"
  | "AFTER_CLOSE"
  | "WEEKEND"
  | "HOLIDAY"
  | "OPEN";

export interface MarketCheckResult {
  allowed: boolean;
  reason: MarketBlockReason;
  message: string;
}

const MARKET_OPEN_MINUTES = 9 * 60 + 15; // 555
const MARKET_CLOSE_MINUTES = 15 * 60 + 30; // 930

// Keep in sync with backend/data/nse_trading_holidays.json (YYYY-MM-DD for IST dates)
const KNOWN_HOLIDAYS: Record<string, string[]> = {
  "2025": [
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-08-15", "2025-08-27",
    "2025-10-02", "2025-10-20", "2025-10-21", "2025-11-05", "2025-12-25"
  ],
  "2026": [
    "2026-01-26", "2026-02-17", "2026-03-03", "2026-03-20", "2026-04-02",
    "2026-04-03", "2026-04-06", "2026-04-14", "2026-05-01", "2026-08-15",
    "2026-08-28", "2026-10-02", "2026-10-19", "2026-10-20", "2026-11-11", "2026-12-25"
  ],
  "2027": [
    "2027-01-26", "2027-02-26", "2027-03-12", "2027-03-29", "2027-04-02",
    "2027-04-14", "2027-04-26", "2027-05-01", "2027-08-15", "2027-08-17",
    "2027-10-02", "2027-10-08", "2027-10-19", "2027-11-05", "2027-12-25"
  ],
};

function getISTDateParts(d: Date = new Date()) {
  // Use Intl to get IST components without full tz library
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
  const weekday = get("weekday"); // e.g. "Sun"

  const dateStr = `${year}-${month}-${day}`;
  const minutesSinceMidnight = hour * 60 + minute;

  const isWeekend = weekday === "Sat" || weekday === "Sun";

  return { dateStr, year, minutesSinceMidnight, isWeekend };
}

function isKnownHoliday(dateStr: string, year: string): boolean {
  const list = KNOWN_HOLIDAYS[year] || [];
  return list.includes(dateStr);
}

export function checkCanPlaceBuyOrder(now: Date = new Date()): MarketCheckResult {
  const { dateStr, year, minutesSinceMidnight, isWeekend } = getISTDateParts(now);

  if (isWeekend) {
    return {
      allowed: false,
      reason: "WEEKEND",
      message:
        "The stock market is closed today.\nBuy orders cannot be placed on weekends.",
    };
  }

  if (isKnownHoliday(dateStr, year)) {
    return {
      allowed: false,
      reason: "HOLIDAY",
      message:
        "Today is an official stock market holiday.\nBuy orders cannot be placed because the exchange is closed.",
    };
  }

  if (minutesSinceMidnight < MARKET_OPEN_MINUTES) {
    return {
      allowed: false,
      reason: "BEFORE_OPEN",
      message:
        "Market has not opened yet.\n\n" +
        "Buy orders can only be placed during market hours (9:15 AM – 3:30 PM IST).\n\n" +
        "Please try again after the market opens.",
    };
  }

  if (minutesSinceMidnight > MARKET_CLOSE_MINUTES) {
    return {
      allowed: false,
      reason: "AFTER_CLOSE",
      message:
        "Market is closed.\n\n" +
        "Buy orders cannot be placed after market hours.\n\n" +
        "Please place your order during the next trading session.",
    };
  }

  return { allowed: true, reason: "OPEN", message: "" };
}

export function isMarketOpenForDisplay(now: Date = new Date()): string {
  const check = checkCanPlaceBuyOrder(now);
  if (check.allowed) return "Open";
  if (check.reason === "WEEKEND" || check.reason === "HOLIDAY" || check.reason === "AFTER_CLOSE") {
    return "Closed";
  }
  return "Closed"; // pre-open also treated closed for trading purposes
}

// Helper to show the alert exactly as specified
export function showMarketClosedAlert(result: MarketCheckResult) {
  // Use a clean modal or alert. For existing codebase we use window.alert for minimal change.
  // In real app, replace with a nice toast / modal component.
  alert(result.message);
}

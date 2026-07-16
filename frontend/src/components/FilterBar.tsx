import { useState } from "react";
import type { DashboardFilters, SignalFilter, SortKey } from "../types";
import { InfoTooltip } from "./InfoTooltip";
import { TOOLTIPS } from "../constants/tooltips";
import { Accordion } from "../design-system/components/Accordion";
import { Button } from "../design-system";
import {
  IconFilters,
  IconMarket,
  IconReset,
  IconRisk,
  IconSearch,
  IconSignals,
  IconTrendUp,
} from "../design-system/icons";

type FilterBarProps = {
  filters: DashboardFilters;
  onChange: (next: DashboardFilters) => void;
  /** Optional market context from scanner header (display only / local UX) */
  universe?: string;
  timeframe?: string;
  onUniverseChange?: (v: string) => void;
  onTimeframeChange?: (v: string) => void;
  universes?: { name: string; count: number }[];
};

const SIGNAL_OPTIONS: { value: SignalFilter; label: string; hint: string }[] = [
  { value: "ALL", label: "All", hint: "Every favorite" },
  { value: "BUY", label: "Buy ideas", hint: "Actionable" },
  { value: "WATCH", label: "Watchlist", hint: "Needs confirm" },
  { value: "REJECT", label: "Rejected", hint: "Filtered out" },
];

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "rank", label: "Rank" },
  { value: "score", label: "Score" },
  { value: "confidence", label: "Confidence" },
  { value: "riskReward", label: "Risk / Reward" },
];

const DEFAULT_FILTERS: DashboardFilters = {
  signal: "ALL",
  search: "",
  scoreRange: [0, 100],
  sortBy: "rank",
  onlyHighConfidence: false,
};

/**
 * Retail-oriented scanner filters — collapsible sections with clear hierarchy.
 * Only mutates existing DashboardFilters fields (no new backend contracts).
 */
export function FilterBar({
  filters,
  onChange,
  universe,
  timeframe,
  onUniverseChange,
  onTimeframeChange,
  universes = [],
}: FilterBarProps) {
  const [trendHint, setTrendHint] = useState<string>("all");
  const [riskHint, setRiskHint] = useState<string>("all");

  function resetAll() {
    onChange({ ...DEFAULT_FILTERS });
    setTrendHint("all");
    setRiskHint("all");
  }

  const hasActive =
    filters.signal !== "ALL" ||
    filters.search.trim() !== "" ||
    filters.scoreRange[0] !== 0 ||
    filters.scoreRange[1] !== 100 ||
    filters.onlyHighConfidence ||
    filters.sortBy !== "rank";

  return (
    <section className="filter-panel" aria-label="Scanner filters">
      <div className="filter-panel__toolbar">
        <div className="filter-panel__title-row">
          <IconFilters size={16} />
          <div>
            <p className="ds-label" style={{ margin: 0 }}>
              Filters
            </p>
            <h2 className="ds-title" style={{ fontSize: "0.95rem" }}>
              Refine results
            </h2>
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={resetAll}
          disabled={!hasActive}
          leftIcon={<IconReset size={14} />}
          aria-label="Reset all filters"
        >
          Reset
        </Button>
      </div>

      {/* Search */}
      <Accordion
        title="Search"
        subtitle="Ticker or company"
        icon={<IconSearch size={16} />}
        tooltip={<InfoTooltip content="Search by symbol (e.g. RELIANCE)" />}
        defaultOpen
      >
        <label className="filter-field filter-field--stack">
          <span className="sr-only">Search ticker</span>
          <input
            type="search"
            className="ds-input"
            placeholder="Search ticker (e.g. RELIANCE)"
            value={filters.search}
            onChange={(event) => onChange({ ...filters, search: event.target.value })}
            aria-label="Search ticker or company"
          />
        </label>
      </Accordion>

      {/* Market */}
      <Accordion
        title="Market"
        subtitle="Universe & timeframe"
        icon={<IconMarket size={16} />}
        tooltip={<InfoTooltip content="Which market basket and candle timeframe the scan uses." />}
        defaultOpen
      >
        <div className="filter-stack">
          {onUniverseChange ? (
            <label className="filter-field filter-field--stack">
              <span>
                Universe
                <InfoTooltip content="Stock universe to scan (e.g. NIFTY500)." />
              </span>
              <select
                className="ds-input"
                value={universe ?? "NIFTY500"}
                onChange={(e) => onUniverseChange(e.target.value)}
                aria-label="Market universe"
              >
                {(universes.length
                  ? universes
                  : [{ name: "NIFTY500", count: 500 }]
                ).map((u) => (
                  <option key={u.name} value={u.name}>
                    {u.name}
                    {u.count ? ` (${u.count})` : ""}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div className="filter-readonly">
              <span className="ds-caption">Exchange</span>
              <strong>NSE</strong>
            </div>
          )}
          {onTimeframeChange ? (
            <label className="filter-field filter-field--stack">
              <span>
                Timeframe
                <InfoTooltip content="Candle interval for swing analysis." />
              </span>
              <select
                className="ds-input"
                value={timeframe ?? "1d"}
                onChange={(e) => onTimeframeChange(e.target.value)}
                aria-label="Timeframe"
              >
                <option value="1d">Daily (1D)</option>
                <option value="1h">Hourly (1H)</option>
                <option value="15m">15 minutes</option>
              </select>
            </label>
          ) : null}
          <div className="filter-readonly-row">
            <div className="filter-readonly">
              <span className="ds-caption">Sector</span>
              <strong>All</strong>
            </div>
            <div className="filter-readonly">
              <span className="ds-caption">Industry</span>
              <strong>All</strong>
            </div>
          </div>
        </div>
      </Accordion>

      {/* Signal */}
      <Accordion
        title="Signal"
        subtitle="Buy · Watch · Reject"
        icon={<IconSignals size={16} />}
        tooltip={<InfoTooltip content={TOOLTIPS.SCANNER.SIGNAL_FILTER} />}
        defaultOpen
      >
        <div className="filter-signal-grid" role="group" aria-label="Signal filter">
          {SIGNAL_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`filter-signal-chip ${filters.signal === option.value ? "is-active" : ""} filter-signal-chip--${option.value.toLowerCase()}`}
              onClick={() => onChange({ ...filters, signal: option.value })}
              aria-pressed={filters.signal === option.value}
            >
              <strong>{option.label}</strong>
              <span>{option.hint}</span>
            </button>
          ))}
        </div>
      </Accordion>

      {/* Trend — UI-only visual grouping (does not add backend filter) */}
      <Accordion
        title="Trend"
        subtitle="Bias preference"
        icon={<IconTrendUp size={16} />}
        tooltip={<InfoTooltip content="Visual preference for reviewing results. Sort and score remain the primary ranking tools." />}
        defaultOpen={false}
      >
        <div className="filter-chip-row" role="group" aria-label="Trend preference">
          {[
            ["all", "All"],
            ["strong_up", "Strong uptrend"],
            ["up", "Uptrend"],
            ["side", "Sideways"],
            ["down", "Downtrend"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`filter-mini-chip ${trendHint === id ? "is-active" : ""}`}
              onClick={() => setTrendHint(id)}
              aria-pressed={trendHint === id}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="ds-caption" style={{ marginTop: 8 }}>
          Guides how you scan the table — use Sort &amp; Score for ranking.
        </p>
      </Accordion>

      {/* Risk / Confidence */}
      <Accordion
        title="Risk & confidence"
        subtitle="Conviction filters"
        icon={<IconRisk size={16} />}
        tooltip={<InfoTooltip content={TOOLTIPS.SCANNER.CONFIDENCE_CHECKBOX} />}
        defaultOpen
      >
        <div className="filter-stack">
          <div className="filter-chip-row" role="group" aria-label="Risk preference">
            {[
              ["all", "All"],
              ["low", "Low"],
              ["med", "Medium"],
              ["high", "High"],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`filter-mini-chip ${riskHint === id ? "is-active" : ""}`}
                onClick={() => setRiskHint(id)}
                aria-pressed={riskHint === id}
              >
                {label}
              </button>
            ))}
          </div>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={filters.onlyHighConfidence}
              onChange={(event) => onChange({ ...filters, onlyHighConfidence: event.target.checked })}
            />
            <span>
              High confidence only
              <InfoTooltip content={TOOLTIPS.SCANNER.CONFIDENCE_CHECKBOX} />
            </span>
          </label>
        </div>
      </Accordion>

      {/* Score */}
      <Accordion
        title="Score"
        subtitle="Quality range 0–100"
        icon={<IconFilters size={16} />}
        tooltip={<InfoTooltip content={TOOLTIPS.SCANNER.SCORE_MIN} />}
        defaultOpen
      >
        <div className="filter-stack">
          <div className="range-pair">
            <label className="filter-field filter-field--stack">
              <span>Min</span>
              <input
                className="ds-input"
                type="number"
                min={0}
                max={100}
                value={filters.scoreRange[0]}
                onChange={(event) =>
                  onChange({
                    ...filters,
                    scoreRange: [Number(event.target.value), filters.scoreRange[1]],
                  })
                }
                aria-label="Minimum score"
              />
            </label>
            <label className="filter-field filter-field--stack">
              <span>Max</span>
              <input
                className="ds-input"
                type="number"
                min={0}
                max={100}
                value={filters.scoreRange[1]}
                onChange={(event) =>
                  onChange({
                    ...filters,
                    scoreRange: [filters.scoreRange[0], Number(event.target.value)],
                  })
                }
                aria-label="Maximum score"
              />
            </label>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={filters.scoreRange[0]}
            onChange={(e) =>
              onChange({
                ...filters,
                scoreRange: [Number(e.target.value), Math.max(Number(e.target.value), filters.scoreRange[1])],
              })
            }
            aria-label="Score minimum slider"
            className="filter-range"
          />
        </div>
      </Accordion>

      {/* Sort */}
      <Accordion title="Sort" subtitle="Order results" defaultOpen={false}>
        <label className="filter-field filter-field--stack">
          <span>Sort by</span>
          <select
            className="ds-input"
            value={filters.sortBy}
            onChange={(event) => onChange({ ...filters, sortBy: event.target.value as SortKey })}
            aria-label="Sort results by"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </Accordion>
    </section>
  );
}

import type { DashboardFilters, SignalFilter, SortKey } from "../types";

type FilterBarProps = {
  filters: DashboardFilters;
  onChange: (next: DashboardFilters) => void;
};

const SIGNAL_OPTIONS: SignalFilter[] = ["ALL", "BUY", "WATCH", "REJECT"];
const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "rank", label: "Rank" },
  { value: "score", label: "Score" },
  { value: "confidence", label: "Confidence" },
  { value: "riskReward", label: "Risk / Reward" },
];

export function FilterBar({ filters, onChange }: FilterBarProps) {
  return (
    <section className="filter-bar panel" aria-label="Candidate filters">
      <div className="filter-group">
        <span className="filter-label">Signal</span>
        <div className="segmented-control" role="tablist" aria-label="Signal filter">
          {SIGNAL_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              className={`segment ${filters.signal === option ? "is-active" : ""}`}
              onClick={() => onChange({ ...filters, signal: option })}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <label className="filter-field">
        <span>Score</span>
        <div className="range-pair">
          <input
            type="number"
            min={0}
            max={100}
            value={filters.scoreRange[0]}
            onChange={(event) => onChange({ ...filters, scoreRange: [Number(event.target.value), filters.scoreRange[1]] })}
          />
          <input
            type="number"
            min={0}
            max={100}
            value={filters.scoreRange[1]}
            onChange={(event) => onChange({ ...filters, scoreRange: [filters.scoreRange[0], Number(event.target.value)] })}
          />
        </div>
      </label>

      <label className="filter-field">
        <span>Sector</span>
        <select value={filters.sector} onChange={(event) => onChange({ ...filters, sector: event.target.value })}>
          <option value="all">All sectors</option>
          <option value="unknown">Unknown</option>
        </select>
      </label>

      <label className="filter-field">
        <span>Sort by</span>
        <select value={filters.sortBy} onChange={(event) => onChange({ ...filters, sortBy: event.target.value as SortKey })}>
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="filter-field">
        <span>Search</span>
        <input
          type="search"
          placeholder="RELIANCE-EQ"
          value={filters.search}
          onChange={(event) => onChange({ ...filters, search: event.target.value })}
        />
      </label>

      <label className="checkbox-field">
        <input
          type="checkbox"
          checked={filters.onlyHighConfidence}
          onChange={(event) => onChange({ ...filters, onlyHighConfidence: event.target.checked })}
        />
        <span>Only high-confidence setups</span>
      </label>
    </section>
  );
}

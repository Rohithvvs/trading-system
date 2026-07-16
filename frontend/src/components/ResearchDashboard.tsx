import { useMemo, type ReactNode } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import { InfoTooltip } from "./InfoTooltip";
import { RESEARCH_TOOLTIPS } from "../constants/researchTooltips";

export type ResearchPayload = Record<string, any>;

type Props = {
  research: ResearchPayload | null | undefined;
  symbol: string;
  loading?: boolean;
  error?: string | null;
};

const NA = "Data not available.";

function disp(v: unknown): string {
  if (v === null || v === undefined || v === "") return NA;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return String(v);
}

function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v !== NA && !Number.isNaN(Number(v))) return Number(v);
  return null;
}

function Explain({ id }: { id: keyof typeof RESEARCH_TOOLTIPS }) {
  const t = RESEARCH_TOOLTIPS[id];
  if (!t) return null;
  const content = `What is this? ${t.what}\n\nWhy is it important? ${t.why}\n\nHow should a swing trader use it? ${t.how}`;
  return <InfoTooltip content={content} />;
}

function Section({
  title,
  tipId,
  children,
  className = "",
}: {
  title: string;
  tipId?: keyof typeof RESEARCH_TOOLTIPS;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`subpanel research-section ${className}`}>
      <div className="research-section-header">
        <h3>
          {title}
          {tipId ? <Explain id={tipId} /> : null}
        </h3>
      </div>
      {children}
    </section>
  );
}

function Metric({
  label,
  value,
  tipId,
  tone,
}: {
  label: string;
  value: unknown;
  tipId?: keyof typeof RESEARCH_TOOLTIPS;
  tone?: "pos" | "neg" | "neu";
}) {
  const cls = tone === "pos" ? "is-positive" : tone === "neg" ? "is-risk" : "";
  return (
    <div className={`metric-card research-metric ${cls}`}>
      <span className="section-label">
        {label}
        {tipId ? <Explain id={tipId} /> : null}
      </span>
      <strong>{disp(value)}</strong>
    </div>
  );
}

function ProgressBar({ value, max = 100, label }: { value: number; max?: number; label?: string }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = pct >= 72 ? "var(--positive)" : pct >= 55 ? "var(--warning)" : "var(--negative)";
  return (
    <div className="research-progress">
      {label ? <div className="research-progress-label">{label}</div> : null}
      <div className="research-progress-track">
        <div className="research-progress-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="research-progress-value">{value.toFixed(1)} / {max}</div>
    </div>
  );
}

function Gauge({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, value));
  const color = pct >= 72 ? "var(--positive)" : pct >= 55 ? "var(--warning)" : "var(--negative)";
  return (
    <div className="research-gauge" title={label}>
      <div
        className="research-gauge-ring"
        style={{
          background: `conic-gradient(${color} ${pct * 3.6}deg, var(--surface-3) 0deg)`,
        }}
      >
        <div className="research-gauge-inner">
          <strong>{Math.round(pct)}</strong>
          <span>{label}</span>
        </div>
      </div>
    </div>
  );
}

function FlagGrid({ flags }: { flags: Record<string, boolean> }) {
  return (
    <div className="research-flag-grid">
      {Object.entries(flags).map(([key, on]) => (
        <span key={key} className={`research-flag ${on ? "is-on" : "is-off"}`}>
          {on ? "✓" : "·"} {key.replace(/_/g, " ")}
        </span>
      ))}
    </div>
  );
}

/** Format a number as ₹ price for trading UI (never raw JSON). */
function formatInr(v: unknown): string {
  const n = num(v);
  if (n === null) return "—";
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function humanizeLabel(raw: unknown): string {
  if (raw == null || raw === "") return "Zone";
  return String(raw)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

type ZoneKind = "demand" | "supply";

function zoneTypeBadge(label: string, kind: ZoneKind): { text: string; tone: "demand" | "supply" | "support" | "resistance" } {
  const l = label.toLowerCase();
  if (kind === "demand") {
    if (l.includes("swing")) return { text: "Strong Demand", tone: "demand" };
    if (l.includes("support")) return { text: "Support", tone: "support" };
    return { text: "Demand", tone: "demand" };
  }
  if (l.includes("swing")) return { text: "Resistance", tone: "resistance" };
  if (l.includes("resistance")) return { text: "Resistance", tone: "resistance" };
  return { text: "Supply", tone: "supply" };
}

function ZoneTable({
  title,
  zones,
  kind,
}: {
  title: string;
  zones: Array<Record<string, unknown>>;
  kind: ZoneKind;
}) {
  const rows = Array.isArray(zones) ? zones : [];
  return (
    <div className={`sd-zone-panel sd-zone-panel--${kind}`}>
      <h4 className="sd-zone-title">{title}</h4>
      {rows.length === 0 ? (
        <p className="sd-empty muted-copy">No {kind} zones detected</p>
      ) : (
        <>
          {/* Desktop / tablet table — do NOT use .table-scroll (hidden ≤720px globally) */}
          <div className="sd-zone-scroll">
            <table className="sd-zone-table">
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Price Range</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((z, i) => {
                  const label = humanizeLabel(z.label ?? z.name ?? z.zone);
                  const low = z.zone_low ?? z.low ?? z.price_low;
                  const high = z.zone_high ?? z.high ?? z.price_high;
                  const badge = zoneTypeBadge(label, kind);
                  return (
                    <tr key={`${label}-${i}`}>
                      <td>
                        <span className="sd-zone-name">{label}</span>
                      </td>
                      <td className="number-cell sd-price-range">
                        {formatInr(low)} – {formatInr(high)}
                      </td>
                      <td>
                        <span className={`sd-badge sd-badge--${badge.tone}`}>{badge.text}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {/* Mobile card stack for readability at ≤480px */}
          <div className="sd-zone-cards" aria-hidden="false">
            {rows.map((z, i) => {
              const label = humanizeLabel(z.label ?? z.name ?? z.zone);
              const low = z.zone_low ?? z.low ?? z.price_low;
              const high = z.zone_high ?? z.high ?? z.price_high;
              const badge = zoneTypeBadge(label, kind);
              return (
                <article key={`card-${label}-${i}`} className={`sd-zone-card sd-zone-card--${kind}`}>
                  <div className="sd-zone-card-top">
                    <span className="sd-zone-name">{label}</span>
                    <span className={`sd-badge sd-badge--${badge.tone}`}>{badge.text}</span>
                  </div>
                  <div className="sd-zone-card-range">
                    <span className="section-label">Price Range</span>
                    <strong className="sd-price-range">
                      {formatInr(low)} – {formatInr(high)}
                    </strong>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function EmptyInfo({ message }: { message: string }) {
  return (
    <div className="sd-empty-info" role="status">
      <span className="sd-info-icon" aria-hidden="true" title="Information">
        ℹ
      </span>
      <span>{message}</span>
    </div>
  );
}

function formatLevelList(areas: unknown[]): string {
  return areas
    .map((a) => {
      if (a != null && typeof a === "object") {
        const o = a as Record<string, unknown>;
        const level = o.level ?? o.price ?? o.zone_high ?? o.zone_low;
        const status = o.status ? ` (${humanizeLabel(o.status)})` : "";
        return `${formatInr(level)}${status}`;
      }
      return formatInr(a);
    })
    .join(", ");
}

function parseRetestLevel(item: unknown): { level: number | null; kind: "resistance" | "support" | "unknown" } {
  if (item == null) return { level: null, kind: "unknown" };
  if (typeof item === "number" || typeof item === "string") {
    return { level: num(item), kind: "unknown" };
  }
  if (typeof item === "object") {
    const o = item as Record<string, unknown>;
    const level = num(o.level ?? o.price ?? o.value);
    const t = String(o.type ?? o.side ?? o.label ?? "").toLowerCase();
    if (t.includes("resist") || t.includes("supply")) return { level, kind: "resistance" };
    if (t.includes("support") || t.includes("demand")) return { level, kind: "support" };
    return { level, kind: "unknown" };
  }
  return { level: null, kind: "unknown" };
}

function SupplyDemandPanel({ sd }: { sd: Record<string, any> }) {
  const demand = Array.isArray(sd.demand_zones) ? sd.demand_zones : [];
  const supply = Array.isArray(sd.supply_zones) ? sd.supply_zones : [];
  const breakouts = Array.isArray(sd.breakout_areas) ? sd.breakout_areas : [];
  const breakdowns = Array.isArray(sd.breakdown_areas) ? sd.breakdown_areas : [];
  const retests = Array.isArray(sd.retest_levels) ? sd.retest_levels : [];
  const liquidity = Array.isArray(sd.liquidity_zones) ? sd.liquidity_zones : [];

  const supportLevel = num(sd.support);
  const resistanceLevel = num(sd.resistance);

  // Map retest values into Resistance / Support without exposing raw CSV/JSON.
  // Classic engine order for plain numbers: [resistance, support].
  let retestResistance: number | null = null;
  let retestSupport: number | null = null;
  if (retests.length > 0) {
    const parsed = retests.map(parseRetestLevel);
    const byRes = parsed.find((p) => p.kind === "resistance" && p.level != null);
    const bySup = parsed.find((p) => p.kind === "support" && p.level != null);
    const unknowns = parsed
      .filter((p) => p.kind === "unknown" && p.level != null)
      .map((p) => p.level as number);
    retestResistance = byRes?.level ?? null;
    retestSupport = bySup?.level ?? null;
    if (retestResistance == null && unknowns[0] != null) retestResistance = unknowns[0];
    if (retestSupport == null && unknowns[1] != null) retestSupport = unknowns[1];
  } else {
    retestResistance = resistanceLevel;
    retestSupport = supportLevel;
  }

  const buySide = liquidity.filter((z: any) => String(z?.type || "").toLowerCase().includes("buy"));
  const sellSide = liquidity.filter((z: any) => String(z?.type || "").toLowerCase().includes("sell"));
  const otherLiq = liquidity.filter(
    (z: any) =>
      !String(z?.type || "").toLowerCase().includes("buy") &&
      !String(z?.type || "").toLowerCase().includes("sell"),
  );

  return (
    <>
      <div className="research-metric-grid">
        <Metric label="Support" value={supportLevel != null ? formatInr(supportLevel) : sd.support} tone="pos" />
        <Metric label="Resistance" value={resistanceLevel != null ? formatInr(resistanceLevel) : sd.resistance} tone="neg" />
      </div>

      <div className="research-two-col sd-zones-grid">
        <ZoneTable title="Demand Zones" zones={demand} kind="demand" />
        <ZoneTable title="Supply Zones" zones={supply} kind="supply" />
      </div>

      <div className="sd-secondary-grid">
        <div className="sd-card">
          <h4 className="sd-card-title">
            Breakout / Breakdown
            <span className="sd-badge sd-badge--neutral">Status</span>
          </h4>
          {breakouts.length === 0 ? (
            <EmptyInfo message="✔ No active breakout zones" />
          ) : (
            <p className="sd-card-body">
              <span className="sd-badge sd-badge--demand">Breakout</span> {formatLevelList(breakouts)}
            </p>
          )}
          {breakdowns.length === 0 ? (
            <EmptyInfo message="✔ No active breakdown zones" />
          ) : (
            <p className="sd-card-body">
              <span className="sd-badge sd-badge--supply">Breakdown</span> {formatLevelList(breakdowns)}
            </p>
          )}
        </div>

        <div className="sd-card">
          <h4 className="sd-card-title">
            Retest Levels
            <span className="sd-badge sd-badge--retest">Retest</span>
          </h4>
          {retestResistance == null && retestSupport == null && retests.length === 0 ? (
            <EmptyInfo message="No retest levels available" />
          ) : (
            <ul className="sd-level-list">
              {retestResistance != null ? (
                <li>
                  <span className="sd-level-label">
                    <span className="sd-bullet" aria-hidden="true">
                      •
                    </span>
                    <span className="sd-badge sd-badge--resistance">Resistance</span>
                  </span>
                  <strong>{formatInr(retestResistance)}</strong>
                </li>
              ) : null}
              {retestSupport != null ? (
                <li>
                  <span className="sd-level-label">
                    <span className="sd-bullet" aria-hidden="true">
                      •
                    </span>
                    <span className="sd-badge sd-badge--support">Support</span>
                  </span>
                  <strong>{formatInr(retestSupport)}</strong>
                </li>
              ) : null}
            </ul>
          )}
        </div>

        <div className="sd-card">
          <h4 className="sd-card-title">
            Liquidity Zones
            <span className="sd-badge sd-badge--liquidity">Liquidity</span>
          </h4>
          {liquidity.length === 0 ? (
            <EmptyInfo message="No liquidity zones detected" />
          ) : (
            <div className="sd-liquidity-grid">
              {buySide.map((z: any, i: number) => (
                <div key={`buy-${i}`} className="sd-liquidity-item sd-liquidity-item--buy">
                  <span className="sd-badge sd-badge--demand">Buy Side Liquidity</span>
                  <strong>{formatInr(z.level ?? z.price)}</strong>
                </div>
              ))}
              {sellSide.map((z: any, i: number) => (
                <div key={`sell-${i}`} className="sd-liquidity-item sd-liquidity-item--sell">
                  <span className="sd-badge sd-badge--supply">Sell Side Liquidity</span>
                  <strong>{formatInr(z.level ?? z.price)}</strong>
                </div>
              ))}
              {otherLiq.map((z: any, i: number) => (
                <div key={`other-${i}`} className="sd-liquidity-item">
                  <span className="sd-badge sd-badge--liquidity">{humanizeLabel(z.type || "Liquidity")}</span>
                  <strong>{formatInr(z.level ?? z.price)}</strong>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function exportBlob(filename: string, content: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function researchToCsv(research: ResearchPayload, symbol: string): string {
  const rows: string[][] = [["field", "value"]];
  const flat = (obj: any, prefix = "") => {
    if (obj == null) {
      rows.push([prefix, NA]);
      return;
    }
    if (typeof obj !== "object" || Array.isArray(obj)) {
      rows.push([prefix, JSON.stringify(obj)]);
      return;
    }
    Object.entries(obj).forEach(([k, v]) => flat(v, prefix ? `${prefix}.${k}` : k));
  };
  flat({ symbol, ...research });
  return rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
}

export function ResearchDashboard({ research, symbol, loading, error }: Props) {
  const radarData = useMemo(() => {
    const b = research?.swing_score?.breakdown || {};
    return Object.entries(b).map(([name, value]) => ({
      metric: name.replace(/_/g, " "),
      value: typeof value === "number" ? value : 0,
    }));
  }, [research]);

  if (loading) {
    return (
      <section className="subpanel" aria-busy="true" style={{ width: "100%", maxWidth: "100%", minWidth: 0, overflow: "hidden" }}>
        <h3>AI Research</h3>
        <p className="muted-copy">Computing swing research from market data…</p>
        <div className="app-skel" style={{ height: 180, width: "100%", maxWidth: "100%", borderRadius: 12, marginTop: 12 }} />
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap", width: "100%" }}>
          <div className="app-skel" style={{ height: 64, flex: "1 1 30%", minWidth: 120, borderRadius: 8 }} />
          <div className="app-skel" style={{ height: 64, flex: "1 1 30%", minWidth: 120, borderRadius: 8 }} />
          <div className="app-skel" style={{ height: 64, flex: "1 1 30%", minWidth: 120, borderRadius: 8 }} />
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="subpanel">
        <h3>Research failed</h3>
        <p className="muted-copy">{error}</p>
      </section>
    );
  }

  if (!research || research.error) {
    return (
      <section className="subpanel">
        <h3>Research unavailable</h3>
        <p className="muted-copy">
          {research?.message || "Open this stock after a full analysis. The research module extends existing market data only."}
        </p>
      </section>
    );
  }

  const summary = research.ai_research_summary || {};
  const swing = research.swing_score || {};
  const trend = research.trend_analysis || {};
  const sd = research.supply_demand || {};
  const mom = research.momentum_analysis || {};
  const vol = research.volume_analysis || {};
  const volatility = research.volatility || {};
  const pa = research.price_action || {};
  const patterns = research.pattern_detection || [];
  const mtf = research.multi_timeframe || {};
  const risk = research.risk_analysis || {};
  const hold = research.holding_period || {};
  const bt = research.backtesting || {};
  const similar = research.historical_similar_setups || {};
  const aiConf = research.ai_confidence || {};
  const news = research.news_analysis || {};
  const sentiment = research.sentiment_analysis || {};
  const fund = research.fundamental_analysis || {};
  const inst = research.institutional_activity || {};
  const checklist = research.checklist || {};
  const insights = research.llm_insights || {};

  const stance = String(summary.stance || aiConf.stance || "Neutral");
  const stanceTone = stance.toLowerCase().includes("bull") ? "pos" : stance.toLowerCase().includes("bear") ? "neg" : "neu";

  const score = num(swing.score) ?? 0;

  function handleExport(kind: "json" | "csv" | "print") {
    const stamp = new Date().toISOString().slice(0, 10);
    if (kind === "json") {
      exportBlob(`${symbol}-research-${stamp}.json`, JSON.stringify(research, null, 2), "application/json");
      return;
    }
    if (kind === "csv") {
      exportBlob(`${symbol}-research-${stamp}.csv`, researchToCsv(research as ResearchPayload, symbol), "text/csv;charset=utf-8");
      return;
    }
    window.print();
  }

  function handlePdfHint() {
    // Browser print-to-PDF avoids new dependencies and works offline
    window.print();
  }

  return (
    <div className="research-dashboard detail-stack" id="research-print-root">
      <div className="research-toolbar no-print">
        <div>
          <p className="section-label">AI Research</p>
          <h2>{symbol} · Swing Research Dashboard</h2>
          <p className="muted-copy">{research.disclaimer}</p>
        </div>
        <div className="research-export-actions">
          <button type="button" className="button ghost-button" onClick={() => handleExport("json")}>
            Export JSON
          </button>
          <button type="button" className="button ghost-button" onClick={() => handleExport("csv")}>
            Export CSV
          </button>
          <button type="button" className="button ghost-button" onClick={handlePdfHint}>
            PDF / Print
          </button>
        </div>
      </div>

      {/* SECTION 1 + 2 */}
      <div className="research-hero-grid">
        <Section title="Research Summary" tipId="ai_research_summary" className="research-hero-main">
          <div className="research-stance-row">
            <span className={`signal-badge signal-${stanceTone === "pos" ? "buy" : stanceTone === "neg" ? "reject" : "watch"}`}>
              {stance}
            </span>
            <span className="helper-chip">Confidence: {disp(summary.stance_confidence || aiConf.label)}</span>
            <span className="helper-chip">Swing Score: {disp(swing.score)} / 100</span>
          </div>
          <p className="research-narrative">{disp(summary.narrative)}</p>
          <div className="research-metric-grid">
            <Metric label="What company does" value={summary.company_does} tipId="company_overview" />
            <Metric label="Business model" value={summary.business_model} />
            <Metric label="Industry" value={summary.industry} />
            <Metric label="Sector" value={summary.sector} />
            <Metric label="Competitive advantage" value={summary.competitive_advantage} />
            <Metric label="Market position" value={summary.current_market_position} />
            <Metric label="Growth opportunities" value={summary.growth_opportunities} />
            <Metric label="Short-term outlook" value={summary.short_term_outlook} />
            <Metric label="Medium-term outlook" value={summary.medium_term_outlook} />
            <Metric label="Long-term outlook" value={summary.long_term_outlook} />
          </div>
          {Array.isArray(summary.risks) ? (
            <ul className="reason-list">
              {summary.risks.map((r: string) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          ) : null}
        </Section>

        <Section title="Swing Trade Score" tipId="swing_score" className="research-hero-side">
          <Gauge value={score} label="Swing" />
          <ProgressBar value={score} label="Overall" />
          <div className="research-breakdown">
            {Object.entries(swing.breakdown || {}).map(([k, v]) => (
              <div key={k} className="research-breakdown-row">
                <span>{k.replace(/_/g, " ")}</span>
                <ProgressBar value={typeof v === "number" ? v : 0} />
              </div>
            ))}
          </div>
          {radarData.length ? (
            <div className="research-radar">
              <ResponsiveContainer width="100%" height={220}>
                <RadarChart data={radarData}>
                  <PolarGrid />
                  <PolarAngleAxis dataKey="metric" tick={{ fontSize: 10, fill: "var(--text-muted)" }} />
                  <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                  <Radar dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.35} />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          ) : null}
        </Section>
      </div>

      {/* Meters */}
      <div className="research-meters">
        <Gauge value={num(swing.breakdown?.momentum) ?? 0} label="Momentum" />
        <Gauge value={num(swing.breakdown?.risk) ?? 0} label="Risk quality" />
        <Gauge value={num(swing.breakdown?.ai_confidence) ?? 0} label="AI conf." />
        <Gauge value={score} label="Trade quality" />
      </div>

      {/* Trend */}
      <Section title="Trend Analysis" tipId="trend_analysis">
        <div className="research-metric-grid">
          <Metric label="Current Trend" value={trend.current_trend} tone={String(trend.current_trend || "").includes("Bull") ? "pos" : String(trend.current_trend || "").includes("Bear") ? "neg" : "neu"} />
          <Metric label="20 EMA" value={trend.ema_20} tipId="ema" />
          <Metric label="50 EMA" value={trend.ema_50} tipId="ema" />
          <Metric label="100 EMA" value={trend.ema_100} tipId="ema" />
          <Metric label="200 EMA" value={trend.ema_200} tipId="ema" />
          <Metric label="EMA alignment" value={trend.ema_alignment} />
          <Metric label="Golden Cross" value={trend.golden_cross ? "Yes" : "No"} />
          <Metric label="Death Cross" value={trend.death_cross ? "Yes" : "No"} />
          <Metric label="Trend Strength" value={trend.trend_strength} />
          <Metric label="ADX" value={trend.adx} tipId="adx" />
          <Metric label="Trend Quality" value={trend.trend_quality} />
        </div>
      </Section>

      {/* Supply demand — human-readable cards/tables only (never raw JSON) */}
      <Section title="Supply & Demand" tipId="supply_demand">
        <SupplyDemandPanel sd={sd} />
      </Section>

      {/* Momentum / Volume / Volatility */}
      <div className="research-three-col">
        <Section title="Momentum" tipId="momentum">
          <div className="research-metric-grid compact">
            <Metric label="RSI" value={mom.rsi} tipId="rsi" />
            <Metric label="MACD" value={mom.macd} tipId="macd" />
            <Metric label="MACD Signal" value={mom.macd_signal} />
            <Metric label="MACD Histogram" value={mom.macd_histogram} />
            <Metric label="Stochastic RSI" value={mom.stochastic_rsi} />
            <Metric label="CCI" value={mom.cci} />
            <Metric label="Momentum" value={mom.momentum} />
            <Metric label="ROC" value={mom.roc} />
            <Metric label="Direction" value={mom.momentum_direction} />
            <Metric label="Strength" value={mom.momentum_strength} />
          </div>
        </Section>
        <Section title="Volume" tipId="volume">
          <div className="research-metric-grid compact">
            <Metric label="Current Volume" value={vol.current_volume} />
            <Metric label="Average Volume" value={vol.average_volume} />
            <Metric label="Volume Ratio" value={vol.volume_ratio} />
            <Metric label="Delivery %" value={vol.delivery_pct} />
            <Metric label="Volume Breakout" value={vol.volume_breakout ? "Yes" : "No"} />
            <Metric label="OBV" value={vol.obv} tipId="obv" />
            <Metric label="Volume Trend" value={vol.volume_trend} />
            <Metric label="Accumulation" value={vol.accumulation ? "Yes" : "No"} />
            <Metric label="Distribution" value={vol.distribution ? "Yes" : "No"} />
          </div>
        </Section>
        <Section title="Volatility" tipId="volatility">
          <div className="research-metric-grid compact">
            <Metric label="ATR" value={volatility.atr} tipId="atr" />
            <Metric label="ATR %" value={volatility.atr_pct} />
            <Metric label="BB Upper" value={volatility.bollinger_bands?.upper} />
            <Metric label="BB Mid" value={volatility.bollinger_bands?.mid} />
            <Metric label="BB Lower" value={volatility.bollinger_bands?.lower} />
            <Metric label="Band Width" value={volatility.band_width} />
            <Metric label="Volatility Score" value={volatility.volatility_score} />
            <Metric
              label="Expected Swing Range"
              value={
                volatility.expected_swing_range && typeof volatility.expected_swing_range === "object"
                  ? `${volatility.expected_swing_range.low} – ${volatility.expected_swing_range.high}`
                  : volatility.expected_swing_range
              }
            />
          </div>
        </Section>
      </div>

      {/* Price action + patterns */}
      <Section title="Price Action" tipId="price_action">
        <FlagGrid flags={pa} />
      </Section>

      <Section title="Pattern Detection" tipId="patterns">
        {/* Desktop/tablet table */}
        <div className="table-scroll">
          <table className="candidate-table">
            <thead>
              <tr>
                <th>Pattern</th>
                <th>Confidence %</th>
                <th>Target</th>
                <th>Invalidation</th>
              </tr>
            </thead>
            <tbody>
              {(patterns as any[]).map((p) => (
                <tr key={`${p.pattern}-${p.confidence_pct}`}>
                  <td>{p.pattern}</td>
                  <td className="number-cell">{disp(p.confidence_pct)}</td>
                  <td className="number-cell">{disp(p.target)}</td>
                  <td className="number-cell">{disp(p.invalidation)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Mobile cards (hidden on desktop, shown ≤480px via CSS) */}
        <div className="pattern-cards">
          {(patterns as any[]).map((p) => (
            <div key={`${p.pattern}-${p.confidence_pct}`} className="pattern-card">
              <div className="pattern-card-header">{p.pattern}</div>
              <div className="pattern-card-body">
                <div className="pattern-card-row">
                  <span>Confidence</span>
                  <strong>{disp(p.confidence_pct)}%</strong>
                </div>
                <div className="pattern-card-row">
                  <span>Target</span>
                  <strong>{disp(p.target)}</strong>
                </div>
                <div className="pattern-card-row">
                  <span>Invalidation</span>
                  <strong>{disp(p.invalidation)}</strong>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* Multi TF */}
      <Section title="Multi Timeframe Analysis" tipId="multi_timeframe">
        {/* Desktop/tablet table */}
        <div className="table-scroll">
          <table className="candidate-table">
            <thead>
              <tr>
                <th>Timeframe</th>
                <th>Trend</th>
                <th>Momentum</th>
                <th>Volume</th>
                <th>Support</th>
                <th>Resistance</th>
                <th>Signal</th>
              </tr>
            </thead>
            <tbody>
              {(["daily", "weekly", "monthly"] as const).map((tf) => {
                const row = mtf[tf] || {};
                return (
                  <tr key={tf}>
                    <td>{tf}</td>
                    <td>{disp(row.trend)}</td>
                    <td>{disp(row.momentum)}</td>
                    <td>{disp(row.volume)}</td>
                    <td>{disp(row.support)}</td>
                    <td>{disp(row.resistance)}</td>
                    <td>{disp(row.signal)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* Mobile cards (hidden on desktop, shown ≤480px via CSS) */}
        <div className="mtf-cards">
          {(["daily", "weekly", "monthly"] as const).map((tf) => {
            const row = mtf[tf] || {};
            return (
              <div key={tf} className="mtf-card">
                <div className="mtf-card-header">{tf}</div>
                <div className="mtf-card-body">
                  <div className="mtf-card-row">
                    <span>Trend</span>
                    <strong>{disp(row.trend)}</strong>
                  </div>
                  <div className="mtf-card-row">
                    <span>Momentum</span>
                    <strong>{disp(row.momentum)}</strong>
                  </div>
                  <div className="mtf-card-row">
                    <span>Volume</span>
                    <strong>{disp(row.volume)}</strong>
                  </div>
                  <div className="mtf-card-row">
                    <span>Support</span>
                    <strong>{disp(row.support)}</strong>
                  </div>
                  <div className="mtf-card-row">
                    <span>Resistance</span>
                    <strong>{disp(row.resistance)}</strong>
                  </div>
                  <div className="mtf-card-row">
                    <span>Signal</span>
                    <strong>{disp(row.signal)}</strong>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      {/* Risk + Holding */}
      <div className="research-two-col">
        <Section title="Risk Analysis" tipId="risk_analysis">
          <div className="research-metric-grid compact">
            <Metric label="Suggested Entry" value={risk.suggested_entry} />
            <Metric label="Stop Loss" value={risk.stop_loss} />
            <Metric label="Target 1" value={risk.target_1} />
            <Metric label="Target 2" value={risk.target_2} />
            <Metric label="Target 3" value={risk.target_3} />
            <Metric label="Risk %" value={risk.risk_pct} />
            <Metric label="Reward %" value={risk.reward_pct} />
            <Metric label="Risk Reward Ratio" value={risk.risk_reward_ratio} tipId="risk_reward" />
            <Metric label="Position Size" value={risk.position_size} />
            <Metric label="Capital Required" value={risk.capital_required} />
          </div>
          <p className="muted-copy">Position size assumes risk amount ₹{disp(risk.risk_amount_assumed)}.</p>
        </Section>
        <Section title="Swing Holding Period" tipId="holding_period">
          <Metric label="Expected Holding" value={`${disp(hold.expected_holding_days)} days`} />
          <div className="table-scroll" style={{ marginTop: 12 }}>
            <table className="candidate-table">
              <thead>
                <tr>
                  <th>Days</th>
                  <th>Probability of target</th>
                </tr>
              </thead>
              <tbody>
                {(hold.options || []).map((o: any) => (
                  <tr key={o.days}>
                    <td>{o.days}</td>
                    <td>{disp(o.probability_of_target)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted-copy">{hold.note}</p>
        </Section>
      </div>

      {/* Backtest + similar */}
      <Section title="Backtesting" tipId="backtesting">
        <p className="muted-copy">Strategy: {disp(bt.strategy_name)}</p>
        <div className="research-three-col">
          {(["past_50", "past_100", "past_250"] as const).map((key) => {
            const w = bt[key] || {};
            return (
              <div key={key} className="metric-card">
                <h4>{key.replace("_", " ").replace("past", "Past")}</h4>
                <div className="research-metric-grid compact">
                  <Metric label="Signals" value={w.signals} />
                  <Metric label="Success Rate" value={typeof w.success_rate === "number" ? `${w.success_rate}%` : w.success_rate} />
                  <Metric label="Avg Return" value={w.average_return} />
                  <Metric label="Avg Loss" value={w.average_loss} />
                  <Metric label="Avg Hold Days" value={w.average_holding_days} />
                  <Metric label="Max DD" value={w.maximum_drawdown} />
                  <Metric label="Sharpe" value={w.sharpe_ratio} />
                  <Metric label="Profit Factor" value={w.profit_factor} />
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="Historical Similar Setups" tipId="similar_setups">
        <div className="research-metric-grid">
          <Metric label="Number of Similar Setups" value={similar.number_of_similar_setups} />
          <Metric label="Win Rate" value={typeof similar.win_rate === "number" ? `${similar.win_rate}%` : similar.win_rate} />
          <Metric label="Failure Rate" value={typeof similar.failure_rate === "number" ? `${similar.failure_rate}%` : similar.failure_rate} />
          <Metric label="Average Return" value={similar.average_return} />
          <Metric label="Median Return" value={similar.median_return} />
          <Metric label="Best Return" value={similar.best_return} />
          <Metric label="Worst Return" value={similar.worst_return} />
          <Metric label="Maximum Drawdown" value={similar.maximum_drawdown} />
        </div>
        <p className="helper-text">{disp(similar.historical_success_note)}</p>
      </Section>

      {/* AI confidence */}
      <Section title="AI Confidence" tipId="ai_confidence">
        <div className="research-stance-row">
          <span className="helper-chip">AI Confidence: {disp(aiConf.label)}</span>
          <span className="helper-chip">Score: {disp(aiConf.score)}</span>
        </div>
        <ul className="reason-list">
          {(aiConf.explanation?.reasons || []).map((r: string) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <p className="research-narrative">{disp(aiConf.explanation?.conclusion)}</p>
      </Section>

      {/* News + Sentiment */}
      <div className="research-two-col">
        <Section title="News Analysis" tipId="news">
          <div className="research-metric-grid compact">
            <Metric label="Overall" value={news.overall_label} />
            <Metric label="Score" value={news.overall_score} />
          </div>
          <p className="muted-copy">{disp(news.summary)}</p>
          <div className="research-news-list">
            {(news.articles || []).slice(0, 5).map((a: any) => (
              <article key={a.url || a.title} className="news-item">
                <div className="news-item-meta">
                  <span>{a.category}</span>
                  <span>Impact: {a.impact}</span>
                </div>
                <h4>{a.title}</h4>
                <p>{a.why_it_matters}</p>
              </article>
            ))}
          </div>
        </Section>
        <Section title="Sentiment Analysis" tipId="sentiment">
          <div className="research-metric-grid compact">
            <Metric label="Overall Score" value={sentiment.overall_sentiment_score} />
            <Metric label="Label" value={sentiment.overall_label} />
            <Metric label="News" value={sentiment.components?.news} />
            <Metric label="Social Media" value={sentiment.components?.social_media} />
            <Metric label="Market Mood" value={sentiment.components?.market_mood} />
            <Metric label="Analyst Ratings" value={sentiment.components?.analyst_ratings} />
          </div>
          <p className="muted-copy">{sentiment.note}</p>
        </Section>
      </div>

      {/* Fundamentals + Institutional */}
      <Section title="Fundamental Analysis" tipId="fundamentals">
        <div className="research-metric-grid">
          <Metric label="Market Cap" value={fund.market_cap} />
          <Metric label="PE" value={fund.pe} />
          <Metric label="PB" value={fund.pb} />
          <Metric label="ROE" value={fund.roe} />
          <Metric label="ROCE" value={fund.roce} />
          <Metric label="Debt" value={fund.debt} />
          <Metric label="Debt Equity" value={fund.debt_equity} />
          <Metric label="EPS" value={fund.eps} />
          <Metric label="Revenue Growth" value={fund.revenue_growth} />
          <Metric label="Profit Growth" value={fund.profit_growth} />
          <Metric label="Cash Flow" value={fund.cash_flow} />
          <Metric label="Promoter Holding" value={fund.promoter_holding} />
          <Metric label="Institution Holding" value={fund.institution_holding} />
          <Metric label="FII" value={fund.fii} />
          <Metric label="DII" value={fund.dii} />
          <Metric label="Dividend Yield" value={fund.dividend_yield} />
          <Metric label="Intrinsic Value" value={fund.intrinsic_value} />
        </div>
        <p className="muted-copy">{disp(fund.summary)}</p>
      </Section>

      <Section title="Institutional Activity" tipId="institutional">
        <div className="research-metric-grid">
          <Metric label="FII Buying" value={inst.fii_buying} />
          <Metric label="FII Selling" value={inst.fii_selling} />
          <Metric label="DII Buying" value={inst.dii_buying} />
          <Metric label="Mutual Funds" value={inst.mutual_funds} />
          <Metric label="Promoter Buying" value={inst.promoter_buying} />
          <Metric label="Promoter Selling" value={inst.promoter_selling} />
          <Metric label="FII Holding %" value={inst.fii_holding_pct} />
          <Metric label="Institution Holding %" value={inst.institution_holding_pct} />
        </div>
        <p className="muted-copy">{inst.note}</p>
      </Section>

      {/* Checklist */}
      <Section title="Trade Checklist" tipId="checklist">
        <div className="checklist-grid">
          {(checklist.items || []).map((item: any) => (
            <article key={item.key} className={`checklist-item ${item.passed ? "is-positive" : "is-risk"}`}>
              <span>{item.passed ? "✓" : "✗"}</span>
              <strong>{item.label}</strong>
            </article>
          ))}
        </div>
        <div className={`research-overall ${checklist.overall === "Trade Ready" ? "is-ready" : "is-avoid"}`}>
          Overall: <strong>{disp(checklist.overall)}</strong> ({checklist.passed}/{checklist.total} passed)
        </div>
      </Section>

      {/* LLM insights */}
      <Section title="LLM Insights" tipId="llm_insights">
        <ul className="reason-list">
          {(insights.bullets || []).map((b: string) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
        <h4>Risks</h4>
        <ul className="reason-list">
          {(insights.risks || []).map((b: string) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
        <p className="research-narrative">{disp(insights.bottom_line)}</p>
      </Section>
    </div>
  );
}

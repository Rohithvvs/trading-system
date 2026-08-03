import { useEffect, useState, type ReactNode } from "react";
import { fetchRe001SymbolLatest } from "../api";

export type Re001DecisionSummary = {
  recommendation_id?: string;
  engine_id?: string;
  engine_version?: string;
  recommendation_state?: string;
  confidence_score?: number;
  strategy_name?: string | null;
  strategy_family?: string | null;
  explanation?: string | null;
  production_action?: string | null;
  reason_codes?: string[] | null;
  market_regime?: string | null;
};

type Props = {
  decision?: Re001DecisionSummary | null;
  /** When analysis lacks lab_engines, optionally resolve latest persisted decision. */
  symbol?: string | null;
  emptyMessage?: string;
};

function mapLatestToSummary(raw: Record<string, unknown>): Re001DecisionSummary {
  return {
    recommendation_id: raw.recommendation_id != null ? String(raw.recommendation_id) : undefined,
    engine_id: raw.engine_id != null ? String(raw.engine_id) : "RE-001",
    engine_version: raw.engine_version != null ? String(raw.engine_version) : undefined,
    recommendation_state:
      raw.recommendation_state != null ? String(raw.recommendation_state) : undefined,
    confidence_score:
      typeof raw.confidence_score === "number"
        ? raw.confidence_score
        : raw.confidence_score != null
          ? Number(raw.confidence_score)
          : undefined,
    strategy_name: (raw.strategy_name as string | null | undefined) ?? null,
    strategy_family: (raw.strategy_family as string | null | undefined) ?? null,
    explanation: (raw.explanation as string | null | undefined) ?? null,
    production_action: (raw.production_action as string | null | undefined) ?? null,
    reason_codes: Array.isArray(raw.reason_codes) ? (raw.reason_codes as string[]) : null,
    market_regime: (raw.market_regime as string | null | undefined) ?? null,
  };
}

export function Re001DetailSection({
  decision,
  symbol,
  emptyMessage = "No RE-001 lab decision for this symbol.",
}: Props): ReactNode {
  const [fetched, setFetched] = useState<Re001DecisionSummary | null>(null);
  const [fetchAttempted, setFetchAttempted] = useState(false);

  useEffect(() => {
    if (decision) {
      setFetched(null);
      setFetchAttempted(false);
      return;
    }
    const sym = (symbol || "").trim();
    if (!sym) {
      setFetched(null);
      setFetchAttempted(true);
      return;
    }

    let mounted = true;
    setFetchAttempted(false);
    void fetchRe001SymbolLatest(sym)
      .then((raw) => {
        if (!mounted) return;
        setFetched(mapLatestToSummary(raw));
        setFetchAttempted(true);
      })
      .catch(() => {
        if (!mounted) return;
        setFetched(null);
        setFetchAttempted(true);
      });
    return () => {
      mounted = false;
    };
  }, [decision, symbol]);

  const resolved = decision ?? fetched;

  if (!resolved) {
    // Avoid flash of empty while optional fallback is in flight.
    if (!decision && symbol && !fetchAttempted) {
      return (
        <section className="ds-card" data-testid="re001-detail-loading" aria-label="RE-001 lab decision">
          <p className="ds-label">Lab · RE-001</p>
          <p className="text-sm opacity-70">Checking lab decision…</p>
        </section>
      );
    }
    return (
      <section className="ds-card" data-testid="re001-detail-empty" aria-label="RE-001 lab decision">
        <p className="ds-label">Lab · RE-001</p>
        <p className="text-sm opacity-70">{emptyMessage}</p>
      </section>
    );
  }

  const state = resolved.recommendation_state ?? "—";
  return (
    <section className="ds-card" data-testid="re001-detail" aria-label="RE-001 lab decision">
      <p className="ds-label">Lab · RE-001 (experimental)</p>
      <div className="grid gap-2 text-sm">
        <div>
          <strong>State:</strong> {state}
        </div>
        <div>
          <strong>Confidence:</strong>{" "}
          {resolved.confidence_score != null ? resolved.confidence_score.toFixed(2) : "—"}
        </div>
        <div>
          <strong>Primary strategy:</strong> {resolved.strategy_name || resolved.strategy_family || "—"}
        </div>
        <div>
          <strong>Regime:</strong> {resolved.market_regime || "—"}
        </div>
        <div>
          <strong>vs Production:</strong> {resolved.production_action || "—"} → {state}
        </div>
        {resolved.reason_codes && resolved.reason_codes.length > 0 ? (
          <div>
            <strong>Reasons:</strong> {resolved.reason_codes.join(", ")}
          </div>
        ) : null}
        {resolved.explanation ? (
          <div>
            <strong>Evidence:</strong> {resolved.explanation}
          </div>
        ) : null}
        <div className="opacity-60 text-xs">
          {resolved.engine_id || "RE-001"} v{resolved.engine_version || "?"} · {resolved.recommendation_id || ""}
        </div>
      </div>
    </section>
  );
}

export default Re001DetailSection;

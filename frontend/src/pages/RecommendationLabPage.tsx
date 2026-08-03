import { useCallback, useEffect, useState } from "react";
import { fetchRe001RecentScans, fetchRe001ScanComparison } from "../api";

type ComparisonRow = {
  symbol: string;
  recommendation_id: string;
  production_action?: string | null;
  production_score?: number | null;
  re001_state: string;
  confidence_score: number;
  strategy_name?: string | null;
  is_mismatch?: boolean | null;
};

type ScanSummary = {
  scan_run_id: string;
  decision_count: number;
  latest_created_at?: string | null;
};

export default function RecommendationLabPage() {
  const [scanRunId, setScanRunId] = useState("");
  const [recent, setRecent] = useState<ScanSummary[]>([]);
  const [rows, setRows] = useState<ComparisonRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void fetchRe001RecentScans(20)
      .then((data) => {
        const items = data.items || [];
        setRecent(items);
        if (items[0]?.scan_run_id && !scanRunId) {
          setScanRunId(items[0].scan_run_id);
        }
      })
      .catch(() => {
        /* empty lab is expected when RE-001 is OFF */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async () => {
    if (!scanRunId.trim()) {
      setError("Enter or select a scan_run_id");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRe001ScanComparison(scanRunId.trim());
      setRows(data.items || []);
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : "Failed to load lab comparison");
    } finally {
      setLoading(false);
    }
  }, [scanRunId]);

  return (
    <div className="p-4 max-w-5xl mx-auto" data-testid="recommendation-lab-page">
      <h1 className="text-xl font-semibold mb-2">Recommendation Lab · RE-001</h1>
      <p className="text-sm opacity-70 mb-4">
        Experimental comparison of production vs RE-001. Production scanner shortlists are unchanged.
        Empty results are expected when RE-001 is disabled (default).
      </p>
      <div className="flex gap-2 mb-4 flex-wrap items-center">
        <select
          className="border rounded px-2 py-1 min-w-[280px]"
          value={scanRunId}
          onChange={(e) => setScanRunId(e.target.value)}
          data-testid="lab-scan-run-select"
        >
          <option value="">Select recent scan…</option>
          {recent.map((s) => (
            <option key={s.scan_run_id} value={s.scan_run_id}>
              {s.scan_run_id} ({s.decision_count})
            </option>
          ))}
        </select>
        <input
          className="border rounded px-2 py-1 min-w-[240px]"
          placeholder="or paste scan_run_id"
          value={scanRunId}
          onChange={(e) => setScanRunId(e.target.value)}
          data-testid="lab-scan-run-id"
        />
        <button type="button" className="ds-button" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Load comparison"}
        </button>
      </div>
      {error ? (
        <p className="text-sm text-red-600 mb-2" role="alert">
          {error}
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left border-b">
              <th className="py-2 pr-2">Symbol</th>
              <th className="py-2 pr-2">Production</th>
              <th className="py-2 pr-2">RE-001</th>
              <th className="py-2 pr-2">Strategy</th>
              <th className="py-2 pr-2">Mismatch</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-4 opacity-60">
                  No lab rows for this scan.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.recommendation_id} className="border-b border-opacity-20">
                  <td className="py-2 pr-2 font-medium">{r.symbol}</td>
                  <td className="py-2 pr-2">
                    {r.production_action ?? "—"}
                    {r.production_score != null ? ` (${r.production_score.toFixed(1)})` : ""}
                  </td>
                  <td className="py-2 pr-2">
                    {r.re001_state} ({r.confidence_score?.toFixed?.(2) ?? r.confidence_score})
                  </td>
                  <td className="py-2 pr-2">{r.strategy_name || "—"}</td>
                  <td className="py-2 pr-2">{r.is_mismatch ? "Yes" : "No"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

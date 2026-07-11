/**
 * Heavy chart widgets — loaded only when overview/performance needs them.
 * Isolates recharts from the initial profile bundle parse.
 */
import { memo, useMemo } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const PIE_COLORS = ["#3b82f6", "#06b6d4", "#a855f7", "#64748b"];

function money(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export const EquityAreaChart = memo(function EquityAreaChart({
  data,
  height = 220,
  showAxes = false,
}: {
  data: { date: string; equity: number }[];
  height?: number;
  showAxes?: boolean;
}) {
  const safe = data?.length ? data : [{ date: "—", equity: 0 }];
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={safe}>
        <defs>
          <linearGradient id="eqFillProf" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="date" hide={!showAxes} tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
        <YAxis hide={!showAxes} domain={["auto", "auto"]} tick={{ fill: "var(--text-muted)", fontSize: 11 }} />
        <Tooltip
          contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }}
          formatter={(v: number) => [money(v), "Equity"]}
        />
        <Area type="monotone" dataKey="equity" stroke="#3b82f6" fill="url(#eqFillProf)" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
});

export const HoldingsPieChart = memo(function HoldingsPieChart({
  data,
  height = 180,
  centerLabel,
}: {
  data: { name: string; value: number }[];
  height?: number;
  centerLabel?: { value: string | number; sub: string };
}) {
  const safe = useMemo(() => (data?.length ? data : [{ name: "Cash", value: 100 }]), [data]);
  return (
    <div className="profile-donut-wrap">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={safe} dataKey="value" nameKey="name" innerRadius={52} outerRadius={78} paddingAngle={3}>
            {safe.map((_, i) => (
              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12 }} />
        </PieChart>
      </ResponsiveContainer>
      {centerLabel ? (
        <div className="profile-donut-center">
          <strong>{centerLabel.value}</strong>
          <span>{centerLabel.sub}</span>
        </div>
      ) : null}
    </div>
  );
});

export { PIE_COLORS };

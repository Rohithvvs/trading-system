import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type {
  BacktestResult,
  CandidateRow,
  DetailTab,
  OHLCVPoint,
  StockAnalysisResult,
  TradePlan,
  SymbolDetail,
} from "../types";
import { fetchSymbolDetail } from "../api";

type StockDetailPanelProps = {
  row: CandidateRow | null;
  onBack?: () => void;
  onSendToPaperTrading?: (row: CandidateRow, suggestedEntry?: number | null) => void;
};

const TABS: { id: DetailTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "technicals", label: "Technicals" },
  { id: "trade-plan", label: "Trade plan" },
  { id: "news", label: "News" },
  { id: "backtest", label: "Backtest" },
  { id: "chart", label: "Chart" },
];

export function StockDetailPanel({ row, onBack, onSendToPaperTrading }: StockDetailPanelProps) {
  const [tab, setTab] = useState<DetailTab>("overview");
  const [riskAmount, setRiskAmount] = useState(5000);
  const [symbolDetail, setSymbolDetail] = useState<SymbolDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    if (!row) return;
    setSymbolDetail(null);
    setDetailError(null);
    setLoadingDetail(true);
    void fetchSymbolDetail(row.symbol)
      .then((d) => {
        if (!mounted) return;
        console.info("[detail] symbol_detail normalized", { symbol: row.symbol, detail: d });
        setSymbolDetail(d);
      })
      .catch((err) => {
        if (!mounted) return;
        setDetailError(err?.message ?? String(err));
      })
      .finally(() => {
        if (!mounted) return;
        setLoadingDetail(false);
      });
    return () => {
      mounted = false;
    };
  }, [row]);

  if (!row) {
    return (
      <section className="panel empty-state">
        <h2>No stock selected</h2>
        <p>Select a row from the candidate table to inspect the recommendation, technicals, trade plan, news, backtest, and chart.</p>
      </section>
    );
  }

  const analysis = row.analysisItem;
  const technical = analysis?.technical.find((item) => item.mode === "swing") ?? analysis?.technical[0];
  const plan = analysis?.recommendation.trade_plans.find((item) => item.mode === "swing") ?? analysis?.recommendation.trade_plans[0];
  const backtest = analysis?.backtests.find((item) => item.mode === "swing") ?? analysis?.backtests[0];
  const rankReason = buildRankContext(row);

  const currentPrice = useMemo(() => {
    const series = symbolDetail?.ohlcv?.length ? symbolDetail!.ohlcv! : analysis?.ohlcv?.length ? analysis!.ohlcv : undefined;
    if (series && series.length) return series[series.length - 1].close;
    return row.entryLow ?? row.entryHigh ?? 0;
  }, [symbolDetail, analysis, row]);

  return (
    <section className="detail-panel panel">
      {onBack ? (
        <div className="detail-toolbar">
          <button type="button" className="button ghost-button detail-back-button" onClick={onBack}>
            Back to scan results
          </button>
        </div>
      ) : null}
      <div className="detail-header">
        <div>
          <p className="section-label">Selected stock</p>
          <div className="detail-title-row">
            <h2>{row.symbol}</h2>
            <span className={`signal-badge signal-${row.signal.toLowerCase()}`}>{row.signal}</span>
          </div>
          <p className="detail-summary">{row.recommendationSummary}</p>
        </div>
        <div className="detail-header-metrics">
          <MetricTile label="Score" value={row.score.toFixed(1)} help="Weighted final score after full analysis." />
          <MetricTile
            label="Confidence"
            value={row.confidence === null ? "--" : `${Math.round(row.confidence * 100)}%`}
            help="How strongly the recommendation layer supports this setup."
          />
          <MetricTile
            label="Risk / Reward"
            value={row.riskReward === null ? "--" : row.riskReward.toFixed(2)}
            help="Potential upside compared to stop-loss risk."
          />
          <MetricTile label="Rank" value={row.rank ?? "--"} help="Position in the current shortlist." />
          <MetricTile label="Readiness" value={row.tradeReadiness} help="Practical action label after data, signal, and risk checks." />
        </div>
      </div>

      {onSendToPaperTrading && (row.signal === "BUY" || row.signal === "WATCH") ? (
        <div className="detail-toolbar">
            <button className="btn" onClick={() => onSendToPaperTrading ? onSendToPaperTrading(row, currentPrice ?? undefined) : window.alert("Send to paper trading")}>
                Send to paper trading
            </button>
        </div>
      ) : null}

      <div className="detail-tabs" role="tablist" aria-label="Stock detail tabs">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`detail-tab ${tab === item.id ? "is-active" : ""}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="detail-content">
        {tab === "overview" ? (
          <OverviewTab analysis={analysis} row={row} rankReason={rankReason} symbolDetail={symbolDetail} currentPrice={currentPrice} loadingDetail={loadingDetail} onSendToPaperTrading={onSendToPaperTrading} />
        ) : null}
        {tab === "technicals" ? (
          <TechnicalsTab technical={technical} row={row} symbolDetail={symbolDetail} />
        ) : null}
        {tab === "trade-plan" ? (
          <TradePlanTab plan={plan} row={row} riskAmount={riskAmount} onRiskAmountChange={setRiskAmount} symbolDetail={symbolDetail} currentPrice={currentPrice} />
        ) : null}
        {tab === "news" ? (
          <NewsTab analysis={analysis} row={row} symbolDetail={symbolDetail} />
        ) : null}
        {tab === "backtest" ? (
          <BacktestTab backtest={backtest} backtestDetail={symbolDetail?.backtest_extras ?? null} />
        ) : null}
        {tab === "chart" ? (
          <ChartTab analysis={analysis} plan={plan} />
        ) : null}
      </div>
    </section>
  );
}

function OverviewTab({
  analysis,
  row,
  rankReason,
  symbolDetail,
  currentPrice,
  loadingDetail,
  onSendToPaperTrading,
}: {
  analysis?: StockAnalysisResult;
  row: CandidateRow;
  rankReason: string;
  symbolDetail?: SymbolDetail | null;
  currentPrice?: number | null;
  loadingDetail?: boolean;
  onSendToPaperTrading?: (row: CandidateRow, suggestedEntry?: number | null) => void;
}) {
  return (
    <div className="detail-grid">
      <section className="subpanel">
        <h3>Recommendation overview</h3>
        <p className="muted-copy">{analysis?.recommendation.summary ?? row.recommendationSummary}</p>
        <div className="reason-columns">
          <ReasonList title="Top reasons" items={analysis?.recommendation.reasoning.bullets ?? [row.recommendationSummary]} />
          <ReasonList
            title="Risk warnings"
            items={analysis?.recommendation.reasoning.risk_factors ?? ["Full analysis did not return extra risk factors for this name."]}
          />
        </div>
        <div className="info-cards" style={{ display: "flex", gap: 12, marginTop: 12 }}>
          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">Sector</span>
            <h4 style={{ margin: 6 }}>{symbolDetail?.sector ?? "-"}</h4>
            <p className="muted-copy">Primary business sector</p>
          </div>
          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">Industry</span>
            <h4 style={{ margin: 6 }}>{symbolDetail?.industry ?? "-"}</h4>
            <p className="muted-copy">Industry classification</p>
          </div>
          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">Market cap</span>
            <h4 style={{ margin: 6 }}>{formatMarketCap(symbolDetail?.market_cap ?? null)}</h4>
            <p className="muted-copy">Reported market capitalization</p>
          </div>
        </div>
      </section>
      <section className="subpanel">
        <h3>Ranking context</h3>
        <div className="score-breakdown">
          <MetricTile label="Final score" value={row.score.toFixed(1)} help="Combined recommendation score." />
          <MetricTile label="Technical" value={row.screenerMatch?.technical_score.toFixed(1) ?? "--"} help="Technical engine strength before recommendation." />
          <MetricTile label="Scanner" value={row.screenerMatch?.screener_score.toFixed(1) ?? "--"} help="Weighted screener score used for shortlisting." />
          <MetricTile
            label="News"
            value={analysis ? `${analysis.news_sentiment_label} (${analysis.news_sentiment_score.toFixed(2)})` : "--"}
            help="How recent news supports or weakens the setup."
          />
        </div>
        <div className="mt-4 space-y-3">
          <div className="flex gap-3">
            <div className="metric-card w-full">
              <span className="section-label">52-week range</span>
              <div className="mt-2">
                <div className="w-full">
                  {symbolDetail?.year52_low != null && symbolDetail?.year52_high != null ? (
                    <RangeBar low={symbolDetail.year52_low} high={symbolDetail.year52_high} current={currentPrice ?? 0} />
                  ) : (
                    <p className="muted-copy">52-week data unavailable</p>
                  )}
                </div>
              </div>
            </div>

            <div className="metric-card w-full" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
              <div>
                <span className="section-label">Company</span>
                <h4 style={{ margin: 6 }}>{symbolDetail?.sector ?? "-"}</h4>
                <p className="muted-copy">{symbolDetail?.industry ?? "-"}</p>
              </div>
              <div>
                <span className="section-label">Market cap</span>
                <h4 style={{ margin: 6 }}>{symbolDetail?.market_cap != null ? new Intl.NumberFormat().format(symbolDetail.market_cap) : "-"}</h4>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <button
              className="button primary-button"
              onClick={() => {
                if (onSendToPaperTrading) {
                  onSendToPaperTrading(row, currentPrice ?? undefined);
                } else {
                  const priceText = currentPrice != null ? currentPrice.toFixed(2) : "N/A";
                  window.alert(`Paper trade entry price: ${priceText}`);
                }
              }}
              disabled={loadingDetail}
            >
              {loadingDetail ? "Loading…" : "Paper Trade"}
            </button>
          </div>
        </div>
        <ConfidenceBreakdown analysis={analysis} />
        <DataQualityBox analysis={analysis} />
        <p className="helper-text">{rankReason}</p>
      </section>
    </div>
  );
}

function TechnicalsTab({
  technical,
  row,
  symbolDetail,
}: {
  technical?: StockAnalysisResult["technical"][number];
  row: CandidateRow;
  symbolDetail?: SymbolDetail | null;
}) {
  const indicators = technical?.indicators ?? {};
  const techExtra = symbolDetail?.technical_extras;
  const hardFailures = [
    !Boolean(indicators["core_trend_filter_pass"]) ? "Trend filter failed" : null,
    !Boolean(indicators["core_momentum_filter_pass"]) ? "Momentum filter failed" : null,
    !Boolean(indicators["basic_liquidity_filter_pass"]) ? "Liquidity filter failed" : null,
  ].filter(Boolean) as string[];

  const tiles = [
    {
      label: "EMA 20",
      value: formatValue(indicators["ema_20"]),
      status: Boolean(indicators["close_above_ema20"]) ? "Passed" : "Failed",
      copy: "Price above EMA 20 keeps the short-term swing trend constructive.",
    },
    {
      label: "Supertrend",
      value: formatValue(indicators["supertrend"]),
      status: Boolean(indicators["supertrend_positive"]) ? "Positive" : "Negative",
      copy: "Supertrend is used as a hard trend confirmation filter.",
    },
    {
      label: "MACD",
      value: `${formatValue(indicators["macd"])} / ${formatValue(indicators["macd_signal"])}`,
      status: Boolean(indicators["macd_positive"]) ? "Positive" : "Negative",
      copy: "MACD above signal supports bullish momentum.",
    },
    {
      label: "RSI",
      value: formatValue(indicators["rsi_14"]),
      status: Boolean(indicators["rsi_supportive"]) ? "Supportive" : "Weak",
      copy: "RSI above 50 supports the current swing bias.",
    },
    {
      label: "SMA trend",
      value: String(indicators["higher_timeframe_trend"] ?? row.trend),
      status: Boolean(indicators["sma_uptrend_20d"]) ? "Rising" : "Flat",
      copy: "A rising SMA trend adds confirmation but does not hard-reject alone.",
    },
    {
      label: "HH / HL structure",
      value: formatValue(indicators["structure_score"]),
      status: Boolean(indicators["structure_supportive"]) ? "Supportive" : "Weak",
      copy: "Higher-high / higher-low structure is a score booster, not a hard filter.",
    },
    {
      label: "Volume",
      value: Boolean(indicators["volume_above_previous_day"]) ? "Expanding" : "Flat",
      status: Boolean(indicators["basic_liquidity_filter_pass"]) ? "Liquid" : "Thin",
      copy: "Liquidity must pass, while volume expansion improves confidence.",
    },
    {
      label: "Candle confirmation",
      value: Boolean(indicators["hammer_or_gravestone"]) ? "Seen" : "None",
      status: Boolean(indicators["hammer_or_gravestone"]) ? "Confirming" : "Optional",
      copy: "Hammer or gravestone are confirmation only and do not reject strong setups by themselves.",
    },
  ];

  // extras mapping
  const atrClass = String((techExtra?.atr_class ?? "")).toLowerCase();
  const atrLabel = atrClass === "low" ? "LOW" : atrClass === "medium" ? "MEDIUM" : atrClass === "high" ? "HIGH" : "-";
  const atrBadgeColor = atrClass === "low" ? "var(--positive)" : atrClass === "medium" ? "var(--warning)" : atrClass === "high" ? "var(--negative)" : "var(--text-muted)";

  function bollingerDisplay(status?: string | null) {
    switch (status) {
      case "below_lower":
        return "Below Lower Band 🔴";
      case "near_lower":
        return "Near Lower Band 🟡";
      case "mid":
        return "Middle of Bands ⚪";
      case "near_upper":
        return "Near Upper Band 🟡";
      case "above_upper":
        return "Above Upper Band 🟢";
      default:
        return status ?? "-";
    }
  }

  function mtfColor(signal?: string | null) {
    if (!signal) return "var(--text-muted)";
    const s = String(signal).toLowerCase();
    if (s.includes("bull") || s === "buy" || s === "bullish") return "var(--positive)";
    if (s.includes("bear") || s === "sell" || s === "bearish") return "var(--negative)";
    return "var(--text-muted)";
  }

  return (
    <div className="detail-stack">
      <section className="subpanel">
        <div className="subpanel-header">
          <h3>Technical decision</h3>
          <div className="meta-inline">
            <span className={`signal-badge signal-${(technical?.signal ?? "bearish").toLowerCase()}`}>{technical?.signal ?? "bearish"}</span>
            <span className="helper-chip">
              <abbr title="Hard filters are core trend, momentum, and liquidity checks that must pass before a stock can be bullish or neutral.">
                Hard filters passed
              </abbr>
              : {Boolean(indicators["hard_filters_pass"]) ? "Yes" : "No"}
            </span>
          </div>
        </div>
        {techExtra ? (
          <div className="mb-3">
            <div className="flex items-center gap-3">
              <div className="metric-card">
                <span className="section-label">ATR</span>
                <div className="mt-2 flex items-center justify-between">
                  <strong>{techExtra.atr != null ? techExtra.atr.toFixed(4) : "--"}</strong>
                  <span
                    className="px-2 py-1 rounded text-sm"
                    style={{
                      background: techExtra.atr_class === "low" ? "var(--positive)" : techExtra.atr_class === "medium" ? "var(--warning)" : "var(--negative)",
                      color: "var(--text)",
                    }}
                  >
                    {String(techExtra.atr_class ?? "-").toUpperCase()}
                  </span>
                </div>
                <p className="muted-copy">ATR %: {techExtra.atr_pct != null ? `${techExtra.atr_pct.toFixed(2)}%` : "--"}</p>
              </div>

              <div className="metric-card">
                <span className="section-label">Bollinger</span>
                <div className="mt-2">
                  <strong>{techExtra.bollinger_status ?? "--"}</strong>
                  <p className="muted-copy">Position relative to bands</p>
                </div>
              </div>

              <div className="metric-card">
                <span className="section-label">Multi-timeframe</span>
                <div className="mt-2">
                  <div className="flex gap-2">
                    <div className="status-pill" style={{ display: "flex", flexDirection: "column" }}>
                      <span className="muted-copy">Daily</span>
                      <strong>{techExtra.multi_timeframe?.daily ?? "-"}</strong>
                    </div>
                    <div className="status-pill" style={{ display: "flex", flexDirection: "column" }}>
                      <span className="muted-copy">Weekly</span>
                      <strong>{techExtra.multi_timeframe?.weekly ?? "-"}</strong>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ) : null}
        <div className="score-breakdown">
          <MetricTile label="Technical score" value={technical?.score.toFixed(1) ?? row.screenerMatch?.technical_score.toFixed(1) ?? "--"} help="Overall technical strength." />
          <MetricTile label="Trend" value={row.trend} help="Trend combines EMA, Supertrend, and higher timeframe alignment." />
          <MetricTile label="Momentum" value={row.momentum} help="Momentum uses MACD and RSI support." />
          <MetricTile label="Structure" value={formatValue(indicators["structure_score"])} help="Structure score counts recent HH/HL confirmations." />
        </div>
        <p className="helper-text">
          {technical?.summary ??
            "This stock only has scanner-stage evidence because the full technical explanation was not returned."}
        </p>
        {hardFailures.length ? (
          <div className="warning-box">
            <strong>Hard filter fail reasons</strong>
            <ul>
              {hardFailures.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="subpanel">
        <h3>Trade confidence checklist</h3>
        <div className="checklist-grid">
          {buildTechnicalChecklist(indicators, row).map((item) => (
            <article key={item.label} className={`checklist-item ${item.passed ? "is-positive" : "is-risk"}`}>
              <span>{item.passed ? "Pass" : "Check"}</span>
              <strong>{item.label}</strong>
              <p>{item.copy}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="indicator-grid-panel">
        {tiles.map((tile) => (
          <article key={tile.label} className="indicator-tile">
            <div className="indicator-header">
              <h4>{tile.label}</h4>
              <span className={`status-tag ${tile.status === "Failed" || tile.status === "Negative" || tile.status === "Weak" ? "is-risk" : "is-positive"}`}>
                {tile.status}
              </span>
            </div>
            <strong>{tile.value}</strong>
            <p>{tile.copy}</p>
          </article>
        ))}
      </section>

      <section className="subpanel">
        <h3>Technical extras</h3>
        <div className="flex gap-3">
          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">ATR</span>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8 }}>
              <strong>{techExtra?.atr != null ? techExtra.atr.toFixed(4) : "--"}</strong>
              <span style={{ background: atrBadgeColor, color: "var(--text)", padding: "4px 8px", borderRadius: 6 }}>{atrLabel}</span>
            </div>
            <p className="muted-copy">{techExtra?.atr_pct != null ? `ATR %: ${techExtra.atr_pct.toFixed(2)}%` : "ATR %: --"}</p>
          </div>

          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">Bollinger</span>
            <div className="mt-2">
              <strong>{bollingerDisplay(techExtra?.bollinger_status)}</strong>
              <p className="muted-copy">Position relative to Bollinger Bands</p>
            </div>
          </div>

          <div className="metric-card" style={{ flex: 1 }}>
            <span className="section-label">Multi-timeframe</span>
            <div className="mt-2">
              <table style={{ width: "100%" }}>
                <tbody>
                  <tr>
                    <td style={{ padding: "6px 8px" }}>Daily</td>
                    <td style={{ padding: "6px 8px", textAlign: "right", color: mtfColor(techExtra?.multi_timeframe?.daily) }}>{techExtra?.multi_timeframe?.daily ?? "-"}</td>
                  </tr>
                  <tr>
                    <td style={{ padding: "6px 8px" }}>Weekly</td>
                    <td style={{ padding: "6px 8px", textAlign: "right", color: mtfColor(techExtra?.multi_timeframe?.weekly) }}>{techExtra?.multi_timeframe?.weekly ?? "-"}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function ConfidenceBreakdown({ analysis }: { analysis?: StockAnalysisResult }) {
  const breakdown = analysis?.confidence_breakdown ?? {};
  return (
    <div className="confidence-box">
      <h4>Confidence breakdown</h4>
      <div className="score-breakdown">
        <MetricTile label="Technical score" value={formatValue(breakdown.technical_score)} help="Raw technical engine score before weighting." />
        <MetricTile label="Technical part" value={formatValue(breakdown.technical_component)} help="Technical score contribution to final recommendation." />
        <MetricTile label="Sentiment part" value={formatValue(breakdown.sentiment_component)} help="News sentiment contribution to final score." />
        <MetricTile label="Backtest part" value={formatValue(breakdown.backtest_component)} help="Backtest contribution to final score." />
      </div>
    </div>
  );
}

function DataQualityBox({ analysis }: { analysis?: StockAnalysisResult }) {
  const quality = analysis?.data_quality ?? {};
  const mockWarning = Boolean(quality.mock_warning);
  return (
      <div className={`data-quality-box ${mockWarning ? "is-risk" : "is-positive"}`}>
        <strong>{mockWarning ? "Mock data warning" : "Data quality"}</strong>
        <p>
          Source {String(quality.source ?? analysis?.data_source ?? "unknown")} | candles {String(quality.candles ?? "--")} | Candles fetched: {String(quality.candles_fetched ?? quality.candles ?? "--")} | latest {String(quality.latest_timestamp ?? "--")}
        </p>
        {mockWarning ? <p>Do not place real trades from this result until FYERS live data is confirmed.</p> : null}
      </div>
  );
}

function buildTechnicalChecklist(indicators: Record<string, string | number | boolean>, row: CandidateRow) {
  return [
    {
      label: "Trend alignment",
      passed: Boolean(indicators["close_above_ema20"]) && Boolean(indicators["supertrend_positive"]),
      copy: "Close above EMA 20 and Supertrend positive.",
    },
    {
      label: "Long-term trend",
      passed: String(indicators["higher_timeframe_trend"] ?? row.trend) === "uptrend",
      copy: "Higher timeframe trend should not fight the trade.",
    },
    {
      label: "Momentum",
      passed: Boolean(indicators["macd_positive"]) && Boolean(indicators["rsi_supportive"]),
      copy: "MACD positive and RSI above 50.",
    },
    {
      label: "Volume",
      passed: Boolean(indicators["basic_liquidity_filter_pass"]) && Boolean(indicators["volume_above_previous_day"]),
      copy: "Liquidity passes and participation is expanding.",
    },
    {
      label: "Structure",
      passed: Boolean(indicators["structure_supportive"]),
      copy: "Recent higher-high / higher-low structure is supportive.",
    },
    {
      label: "Risk-reward",
      passed: (row.riskReward ?? 0) >= 2,
      copy: "Prefer at least 1:2 before taking the trade.",
    },
  ];
}

function TradePlanTab({
  plan,
  row,
  riskAmount,
  onRiskAmountChange,
  symbolDetail,
  currentPrice,
}: {
  plan?: TradePlan;
  row: CandidateRow;
  riskAmount: number;
  onRiskAmountChange: (value: number) => void;
  symbolDetail?: SymbolDetail | null;
  currentPrice?: number | null;
}) {
  if (!plan) {
    return (
      <section className="subpanel">
        <h3>No detailed trade plan</h3>
        <p>This name did not return an execution-ready trade plan. That usually means it was rejected before the deeper recommendation stage.</p>
      </section>
    );
  }

  const entryMid = (plan.entry_low + plan.entry_high) / 2;
  const riskPerShare = Math.abs(entryMid - plan.stop_loss);
  const rewardPerShare = Math.abs(plan.target_1 - entryMid);
  const positionSize = riskPerShare > 0 ? Math.floor(riskAmount / riskPerShare) : 0;

  return (
    <div className="detail-stack">
      <section className="tradeplan-hero">
        <div>
          <p className="section-label">Execution plan</p>
          <h3>{plan.setup_type}</h3>
          <p className="muted-copy">{plan.notes}</p>
        </div>
        <div className="tradeplan-grid">
          <MetricTile label="Entry zone" value={`${plan.entry_low.toFixed(2)} - ${plan.entry_high.toFixed(2)}`} help="Preferred swing entry area." />
          <MetricTile label="Stop loss" value={plan.stop_loss.toFixed(2)} help="If price breaks this, the setup is invalidated." />
          <MetricTile label="Target 1" value={plan.target_1.toFixed(2)} help="First realistic swing objective." />
          <MetricTile label="Target 2" value={plan.target_2.toFixed(2)} help="Second objective if momentum continues." />
        </div>
      </section>
      <section className="subpanel">
        <h3>Exit Strategy</h3>
        <div className="muted-copy" style={{ marginTop: 8 }}>
          {`Exit 50% position at Target 1 (₹${plan.target_1.toFixed(2)}). Move stop loss to entry price. Let remaining 50% ride to Target 2 (₹${plan.target_2.toFixed(2)}).`}
        </div>

        <div style={{ marginTop: 12 }}>
          <div className="score-breakdown">
            <MetricTile
              label="Trailing Stop"
              value={
                symbolDetail?.technical_extras?.atr != null
                  ? `₹${Number(symbolDetail.technical_extras.atr).toFixed(2)} below current price (1× ATR)`
                  : "--"
              }
              help="Suggested trailing stop distance using ATR"
            />
            <MetricTile
              label="Suggested Holding"
              value={plan.suggested_holding_days ?? (plan as any).holding_horizon ?? plan.timeframe ?? "--"}
              help="Suggested holding period for the trade"
            />
          </div>
        </div>
      </section>

      <section className="detail-grid">
        <div className="subpanel">
          <h3>Trade mechanics</h3>
          <div className="score-breakdown">
            <MetricTile label="Bias" value={plan.bias} help="Direction of the setup." />
            <MetricTile label="Risk / share" value={riskPerShare.toFixed(2)} help="Distance from entry midpoint to stop loss." />
            <MetricTile label="Reward / share" value={rewardPerShare.toFixed(2)} help="Distance from entry midpoint to first target." />
            <MetricTile label="Risk / Reward" value={plan.risk_reward_ratio.toFixed(2)} help="Higher is better if the setup quality also holds." />
          </div>
          <ReasonList
            title="Invalidation"
            items={row.analysisItem?.recommendation.reasoning.invalidation_signals ?? ["Exit the idea if price loses structure and closes below the planned stop."]}
          />
        </div>

        <div className="subpanel">
          <h3>Position sizing</h3>
          <label className="filter-field">
            <span>Risk amount</span>
            <input type="number" min={100} step={100} value={riskAmount} onChange={(event) => onRiskAmountChange(Number(event.target.value))} />
          </label>
          <div className="score-breakdown">
            <MetricTile label="Suggested quantity" value={positionSize} help="Estimated quantity using risk amount / risk per share." />
            <MetricTile label="Holding horizon" value={plan.timeframe} help="Expected swing holding window." />
            <MetricTile label="Strategy" value={plan.strategy_name} help="Backtest strategy used for context." />
            <MetricTile label="Signal" value={row.signal} help="Recommendation outcome for this setup." />
          </div>
        </div>
      </section>
    </div>
  );
}

function NewsTab({ analysis, row, symbolDetail }: { analysis?: StockAnalysisResult; row: CandidateRow; symbolDetail?: SymbolDetail | null }) {
  const articles = analysis?.news_articles?.slice(0, 3) ?? [];
  const socialSentiment = symbolDetail?.news_extras?.social_sentiment ?? (analysis?.social_sentiment_score ?? null);

  const corporate = (symbolDetail?.news_extras?.corporate_events as Record<string, any> | undefined) ?? (analysis?.corporate_events as Record<string, any> | undefined) ?? {};

  const earnings = corporate?.earnings_date ?? corporate?.earnings ?? corporate?.next_earnings ?? null;
  const exDividend = corporate?.ex_dividend_date ?? corporate?.ex_dividend ?? corporate?.exdiv ?? null;
  const agm = corporate?.agm_date ?? corporate?.agm ?? null;

  function sentimentColor(score?: number | null) {
    if (score == null) return "var(--text-muted)";
    if (score > 0) return "var(--positive)";
    if (score < 0) return "var(--negative)";
    return "var(--text-muted)";
  }

  return (
    <div className="detail-stack">
      <section className="subpanel">
        <div className="subpanel-header">
          <h3>News sentiment</h3>
          <div className="meta-inline">
            <span className={`status-tag ${analysis?.news_sentiment_label === "positive" ? "is-positive" : analysis?.news_sentiment_label === "negative" ? "is-risk" : "is-neutral"}`}>
              {analysis?.news_sentiment_label ?? row.newsSentiment}
            </span>
            <span className="helper-chip">
              {analysis ? analysis.news_sentiment_score.toFixed(2) : "--"}
            </span>
            <span className="helper-chip" style={{ marginLeft: 8, background: sentimentColor(socialSentiment), color: "var(--text)" }}>
              Sentiment Score: {socialSentiment == null ? "--" : String(socialSentiment)}
            </span>
          </div>
        </div>
        <p className="muted-copy">{analysis?.news_summary ?? "No detailed news summary was available for this stock."}</p>
      </section>

      <section className="news-list">
        {articles.length ? (
          articles.map((article) => (
            <article key={article.url} className="news-item">
              <div className="news-item-meta">
                <span>{article.source}</span>
                <time>{new Date(article.published_at).toLocaleString()}</time>
              </div>
              <h4>{article.title}</h4>
              <p>{article.description}</p>
              <a href={article.url} target="_blank" rel="noreferrer">
                Open source
              </a>
            </article>
          ))
        ) : (
          <div className="subpanel">
            <p>
              No articles found from primary source. Try searching: {row.symbol} NSE news —{' '}
              <a href={`https://www.google.com/search?q=${encodeURIComponent(row.symbol + ' NSE news')}`} target="_blank" rel="noreferrer noopener">
                Google search
              </a>
            </p>
            <p className="muted-copy" style={{ marginTop: 8 }}>
              Primary news source returned no results. Use the search link above.
            </p>
          </div>
        )}
      </section>

      <section className="subpanel">
        <h3>Corporate Events</h3>
        {earnings || exDividend || agm ? (
          <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
            <div className="corporate-row"><strong>Earnings Date:</strong> <span className="muted-copy">{earnings ?? 'Not Available'}</span></div>
            <div className="corporate-row"><strong>Ex-Dividend Date:</strong> <span className="muted-copy">{exDividend ?? 'Not Available'}</span></div>
            <div className="corporate-row"><strong>AGM Date:</strong> <span className="muted-copy">{agm ?? 'Not Available'}</span></div>
          </div>
        ) : (
          <p className="muted-copy" style={{ marginTop: 8 }}>
            Corporate events data will be available when a data provider is connected.
          </p>
        )}
      </section>
    </div>
  );
}

function BacktestTab({ backtest, backtestDetail }: { backtest?: BacktestResult; backtestDetail?: any | null }) {
  const dataSource = backtestDetail ?? backtest ?? null;
  if (!dataSource) {
    return (
      <section className="subpanel">
        <h3>No backtest support</h3>
        <p>This stock did not return a swing backtest result, so the recommendation is relying more heavily on scanner and technical evidence.</p>
      </section>
    );
  }

  // normalize equity series (support {label,equity} or {date,equity})
  const rawEquity = dataSource.equity_curve ?? backtest?.equity_curve ?? [];
  const equityData = (rawEquity as any[]).map((p: any) => ({ label: p.label ?? p.date ?? String(p[0] ?? ""), equity: Number(p.equity ?? p.value ?? p[1] ?? 0) }));

  const monthly = dataSource.monthly_returns ?? [];
  const bestTrade = dataSource.best_trade ?? null;
  const worstTrade = dataSource.worst_trade ?? null;
  const sharpe = dataSource.sharpe_ratio ?? backtest?.sharpe_ratio ?? 0;
  const profitFactor = dataSource.profit_factor ?? backtest?.profit_factor ?? 0;

  // explicit colors to avoid SVG/CSS var issues
  const upColor = "#38b26d"; // green
  const downColor = "#c05c54"; // red
  const neutralColor = "#ffffff";

  const barColors = equityData.map((point: any, idx: number) => {
    if (idx === 0) return upColor;
    const prev = equityData[idx - 1];
    const cur = Number(point.equity ?? 0);
    const p = Number(prev.equity ?? 0);
    if (Number.isNaN(cur) || Number.isNaN(p)) return neutralColor;
    return cur >= p ? upColor : downColor;
  });

  const monthlyColor = (r: number | null | undefined) => {
    if (r == null || Number.isNaN(Number(r))) return "transparent";
    if (r > 0.03) return "var(--positive)"; // dark green
    if (r >= 0) return "var(--positive-soft)"; // light green
    if (r >= -0.03) return "var(--negative-soft)"; // light red
    return "var(--negative)"; // dark red
  };

  return (
    <div className="detail-stack">
      <section className="detail-grid">
        <div className="subpanel">
          <h3>Backtest strength</h3>
          <div className="score-breakdown">
            <MetricTile label="Win rate" value={`${(dataSource.win_rate ?? backtest?.win_rate ?? 0).toFixed(1)}%`} help="Share of historical winning trades." />
            <MetricTile label="Average return" value={`${(dataSource.total_return ?? backtest?.total_return ?? 0).toFixed(1)}%`} help="Total return in the backtest window." />
            <MetricTile label="Max drawdown" value={`${(dataSource.max_drawdown ?? backtest?.max_drawdown ?? 0).toFixed(1)}%`} help="Worst peak-to-trough decline." />
            <MetricTile label="Total trades" value={dataSource.trade_count ?? backtest?.trade_count ?? 0} help="Sample size of historical trades." />
            <MetricTile label="Sharpe" value={Number(sharpe).toFixed(2)} help="Sharpe ratio (approx)." />
            <MetricTile label="Profit factor" value={(profitFactor ?? 0).toFixed(2)} help="Profit factor of strategy." />
          </div>
          <p className="helper-text">
            <abbr title="Backtest strength summarizes how healthy the historical strategy profile looks.">Backtest strength</abbr>: {dataSource.verdict ?? backtest?.verdict ?? "--"}.
          </p>
        </div>

        <div className="subpanel chart-shell">
          <h3>Equity curve</h3>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={equityData}>
              <CartesianGrid strokeDasharray="2 2" vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="equity" radius={[4, 4, 0, 0]}>
                {equityData.map((entry: any, idx: number) => (
                  <Cell key={`cell-${idx}`} fill={barColors[idx]} />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="subpanel">
        <h3>Monthly returns</h3>
        {monthly.length ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 8 }}>
            {monthly.map((m: any) => (
              <div key={m.month} className="p-2 rounded" style={{ background: monthlyColor(m.return), color: "var(--text)", padding: 8 }}>
                <strong>{m.month}</strong>
                <div className="muted-copy">{(m.return * 100).toFixed(1)}%</div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted-copy">Monthly returns not available.</p>
        )}
      </section>

      <section className="detail-grid">
        <div className="subpanel" style={{ borderLeft: bestTrade ? `4px solid ${upColor}` : undefined }}>
          <h3>Best trade</h3>
          {bestTrade ? (
            <div>
              <p>{formatDate(bestTrade.entry_date)} → {formatDate(bestTrade.exit_date)}</p>
              <strong style={{ color: upColor }}>{bestTrade.pnl_percent.toFixed(2)}%</strong>
            </div>
          ) : (
            <p className="muted-copy">No data</p>
          )}
        </div>
        <div className="subpanel" style={{ borderLeft: worstTrade ? `4px solid ${downColor}` : undefined }}>
          <h3>Worst trade</h3>
          {worstTrade ? (
            <div>
              <p>{formatDate(worstTrade.entry_date)} → {formatDate(worstTrade.exit_date)}</p>
              <strong style={{ color: downColor }}>{worstTrade.pnl_percent.toFixed(2)}%</strong>
            </div>
          ) : (
            <p className="muted-copy">No data</p>
          )}
        </div>
      </section>
    </div>
  );
}

function ChartTab({ analysis, plan }: { analysis?: StockAnalysisResult; plan?: TradePlan }) {
  if (!analysis?.ohlcv?.length) {
    return (
      <section className="subpanel">
        <h3>Chart unavailable</h3>
        <p>No candle series was returned for this stock.</p>
      </section>
    );
  }

  const allCandles = analysis.ohlcv;
  const [timeframe, setTimeframe] = useState<"1D" | "1W" | "1M">("1D");
  const [visibleCount, setVisibleCount] = useState<number>(60);

  // adjust default visible counts per timeframe
  useEffect(() => {
    if (timeframe === "1D") setVisibleCount(60);
    else if (timeframe === "1W") setVisibleCount(26);
    else setVisibleCount(12);
  }, [timeframe]);

  function getWeekKey(d: Date) {
    const tmp = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    tmp.setUTCDate(tmp.getUTCDate() + 4 - (tmp.getUTCDay() || 7));
    const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
    const weekNo = Math.ceil((((tmp.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
    return `${tmp.getUTCFullYear()}-W${weekNo}`;
  }

  function resampleCandles(candles: typeof allCandles, tf: string) {
    if (tf === "1D") return candles;
    const groups: Record<string, typeof candles> = {};
    for (const c of candles) {
      const d = new Date(c.timestamp);
      const key = tf === "1W" ? getWeekKey(d) : `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
      groups[key] = groups[key] || [];
      groups[key].push(c);
    }
    const out: typeof candles = [];
    for (const k of Object.keys(groups)) {
      const arr = groups[k];
      const open = arr[0].open;
      const close = arr[arr.length - 1].close;
      const high = Math.max(...arr.map((x) => x.high));
      const low = Math.min(...arr.map((x) => x.low));
      const volume = arr.reduce((s, x) => s + (x.volume ?? 0), 0);
      const timestamp = arr[arr.length - 1].timestamp;
      out.push({ timestamp, open, high, low, close, volume });
    }
    // ensure chronological order
    out.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    return out;
  }

  const resampled = useMemo(() => resampleCandles(allCandles, timeframe), [allCandles, timeframe]);
  const visible = resampled.slice(-visibleCount);

  function zoomIn() {
    setVisibleCount((v) => Math.max(10, Math.floor(v / 2)));
  }
  function zoomOut() {
    setVisibleCount((v) => Math.min(resampled.length, v * 2));
  }

  return (
    <div className="detail-stack">
      <section className="subpanel">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <button className={`button ${timeframe === "1D" ? "is-active" : ""}`} onClick={() => setTimeframe("1D")}>1D</button>
            <button className={`button ${timeframe === "1W" ? "is-active" : ""}`} onClick={() => setTimeframe("1W")}>1W</button>
            <button className={`button ${timeframe === "1M" ? "is-active" : ""}`} onClick={() => setTimeframe("1M")}>1M</button>
          </div>
          <div>
            <button className="button" onClick={zoomIn}>−</button>
            <span style={{ margin: "0 8px" }}>{visible.length} bars</span>
            <button className="button" onClick={zoomOut}>+</button>
          </div>
        </div>
        <h3 style={{ marginTop: 12 }}>Price structure</h3>
        <p className="helper-text">Candles, EMA 20, Supertrend flips, zoom and timeframe controls are available.</p>
      </section>
      <CandlestickChart candles={visible} plan={plan} />
    </div>
  );
}

function ReasonList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h4>{title}</h4>
      <ul className="reason-list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function MetricTile({
  label,
  value,
  help,
}: {
  label: string;
  value: string | number;
  help: string;
}) {
  return (
    <div className="metric-tile">
      <span>
        <abbr title={help}>{label}</abbr>
      </span>
      <strong>{value}</strong>
    </div>
  );
}

function CandlestickChart({ candles, plan }: { candles: OHLCVPoint[]; plan?: TradePlan }) {
  const width = 920;
  const height = 360;
  const volumeHeight = 70;
  const chartTop = 20;
  const chartHeight = height - volumeHeight - 40;
  const allPrices = candles.flatMap((candle) => [candle.high, candle.low]);
  const minPrice = Math.min(...allPrices) * 0.995;
  const maxPrice = Math.max(...allPrices) * 1.005;
  const volumeMax = Math.max(...candles.map((candle) => candle.volume), 1);
  const candleWidth = Math.max(6, width / (candles.length * 1.8));

  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const ema20 = calculateEmaSeries(candles, 20);
  const supertrend = calculateApproxSupertrend(candles, 10, 3);

  const xFor = (index: number) => 30 + (index * (width - 60)) / Math.max(candles.length - 1, 1);
  const yFor = (price: number) => chartTop + ((maxPrice - price) / (maxPrice - minPrice)) * chartHeight;

  const emaPath = buildPath(ema20, xFor, yFor);
  const supertrendPath = buildPath(supertrend, xFor, yFor);
  // detect supertrend flips (direction changes)
  const directions = candles.map((c, i) => (Number(c.close ?? 0) >= Number(supertrend[i] ?? 0) ? "bull" : "bear"));
  const flips: { index: number; type: "bullish" | "bearish" }[] = [];
  for (let i = 1; i < directions.length; i++) {
    if (directions[i] !== directions[i - 1]) {
      flips.push({ index: i, type: directions[i] === "bull" ? "bullish" : "bearish" });
    }
  }
  const tradeLevels = [
    { label: "Entry", value: plan ? (plan.entry_low + plan.entry_high) / 2 : null, className: "chart-line-entry" },
    { label: "Stop", value: plan?.stop_loss ?? null, className: "chart-line-stop" },
    { label: "T1", value: plan?.target_1 ?? null, className: "chart-line-target" },
    { label: "T2", value: plan?.target_2 ?? null, className: "chart-line-target" },
  ].filter((item) => item.value !== null) as { label: string; value: number; className: string }[];

  return (
    <div className="subpanel chart-shell" style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${width} ${height}`} className="price-chart" role="img" aria-label="Swing candlestick chart">
        <rect x="0" y="0" width={width} height={height} fill="transparent" />

        {tradeLevels.map((level) => {
          const y = yFor(level.value);
          return (
            <g key={`${level.label}-${level.value}`}>
              <line x1={20} x2={width - 20} y1={y} y2={y} className={level.className} />
              <text x={width - 16} y={y - 4} className="chart-label">
                {level.label} {level.value.toFixed(2)}
              </text>
            </g>
          );
        })}

        <path d={emaPath} className="chart-line-ema" />
        <path d={supertrendPath} className="chart-line-supertrend" />

        <g className="candles">
          {candles.map((candle, index) => {
            const x = xFor(index);
            const openY = yFor(candle.open);
            const closeY = yFor(candle.close);
            const highY = yFor(candle.high);
            const lowY = yFor(candle.low);
            const isUp = candle.close >= candle.open;
            const bodyTop = Math.min(openY, closeY);
            const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);
            const volumeBarHeight = (candle.volume / volumeMax) * volumeHeight;

            return (
              <g key={`${candle.timestamp}-${index}`}>
                <line x1={x} x2={x} y1={highY} y2={lowY} className={isUp ? "candle-wick-up" : "candle-wick-down"} />
                <rect
                  x={x - candleWidth / 2}
                  y={bodyTop}
                  width={candleWidth}
                  height={bodyHeight}
                  className={isUp ? "candle-body-up" : "candle-body-down"}
                  rx="1"
                />
                <rect
                  x={x - candleWidth / 2}
                  y={height - volumeBarHeight - 16}
                  width={candleWidth}
                  height={volumeBarHeight}
                  className="volume-bar"
                  rx="1"
                />
              </g>
            );
          })}
        </g>

        {/* supertrend flip markers */}
        {flips.map((f) => {
          const idx = f.index;
          const cx = xFor(idx);
          const c = candles[idx];
          if (!c) return null;
          if (f.type === "bullish") {
            const y = yFor(c.low) + 12;
            return <polygon key={`flip-${idx}`} points={`${cx},${y} ${cx - 6},${y + 10} ${cx + 6},${y + 10}`} fill="#38b26d" />;
          }
          const y = yFor(c.high) - 12;
          return <polygon key={`flip-${idx}`} points={`${cx},${y} ${cx - 6},${y - 10} ${cx + 6},${y - 10}`} fill="#c05c54" />;
        })}

        {/* interactive overlay for crosshair */}
        <rect
          x={20}
          y={chartTop}
          width={width - 40}
          height={chartHeight}
          fill="transparent"
          onMouseMove={(e) => {
            try {
              const rect = (e.target as SVGRectElement).ownerSVGElement!.getBoundingClientRect();
              const x = e.clientX - rect.left;
              const step = Math.max(1, (width - 60) / Math.max(candles.length - 1, 1));
              let idx = Math.round((x - 30) / step);
              idx = Math.max(0, Math.min(candles.length - 1, idx));
              setHoverIndex(idx);
            } catch (_) {
            }
          }}
          onMouseLeave={() => setHoverIndex(null)}
        />

        {/* crosshair lines */}
        {hoverIndex != null && hoverIndex >= 0 && hoverIndex < candles.length ? (
          (() => {
            const cx = xFor(hoverIndex);
            const c = candles[hoverIndex];
            const cy = yFor(c.close);
            return (
              <g key={`hover-${hoverIndex}`}>
                <line x1={cx} x2={cx} y1={chartTop} y2={height - 16} stroke="#9aa7b8" strokeDasharray="3 3" strokeWidth={1} />
                <line x1={20} x2={width - 20} y1={cy} y2={cy} stroke="#9aa7b8" strokeDasharray="3 3" strokeWidth={1} />
              </g>
            );
          })()
        ) : null}
      </svg>

      {/* tooltip (HTML overlay) */}
      {hoverIndex != null && hoverIndex >= 0 && hoverIndex < candles.length ? (
        (() => {
          const c = candles[hoverIndex];
          const cx = xFor(hoverIndex);
          const tooltipLeft = Math.max(8, Math.min(width - 220, cx + 8));
          return (
            <div style={{ position: "absolute", left: tooltipLeft, top: 8, background: "var(--surface)", color: "var(--text)", padding: 8, borderRadius: 6, boxShadow: "var(--shadow)" }}>
              <div style={{ fontWeight: 600 }}>{new Date(c.timestamp).toLocaleString()}</div>
              <div>O: {c.open.toFixed(2)} H: {c.high.toFixed(2)} L: {c.low.toFixed(2)} C: {c.close.toFixed(2)}</div>
              <div className="muted-copy">Vol: {new Intl.NumberFormat().format(c.volume)}</div>
            </div>
          );
        })()
      ) : null}

      <div className="chart-legend">
        <span><i className="legend-swatch legend-ema" /> EMA 20</span>
        <span><i className="legend-swatch legend-supertrend" /> Supertrend</span>
        <span><i className="legend-swatch legend-entry" /> Trade levels</span>
      </div>
    </div>
  );
}

function calculateEmaSeries(candles: OHLCVPoint[], period: number) {
  const multiplier = 2 / (period + 1);
  let previous = candles[0]?.close ?? 0;
  return candles.map((candle, index) => {
    if (index === 0) {
      previous = candle.close;
      return previous;
    }
    previous = candle.close * multiplier + previous * (1 - multiplier);
    return previous;
  });
}

function calculateApproxSupertrend(candles: OHLCVPoint[], period: number, multiplier: number) {
  const trs = candles.map((candle, index) => {
    if (index === 0) {
      return candle.high - candle.low;
    }
    const previousClose = candles[index - 1].close;
    return Math.max(
      candle.high - candle.low,
      Math.abs(candle.high - previousClose),
      Math.abs(candle.low - previousClose),
    );
  });

  let atr = trs[0] ?? 0;
  return candles.map((candle, index) => {
    atr = index === 0 ? trs[0] ?? 0 : ((atr * (period - 1)) + trs[index]) / period;
    const mid = (candle.high + candle.low) / 2;
    return mid - (multiplier * atr);
  });
}

function buildPath(series: number[], xFor: (index: number) => number, yFor: (price: number) => number) {
  return series
    .map((value, index) => `${index === 0 ? "M" : "L"} ${xFor(index)} ${yFor(value)}`)
    .join(" ");
}

function formatValue(value: unknown) {
  if (typeof value === "number") {
    return value.toFixed(2);
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value ?? "--");
}

function formatDate(input?: string | null) {
  if (!input) return "-";
  try {
    const d = new Date(input);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  } catch {
    return String(input);
  }
}

function RangeBar({ low, high, current }: { low: number; high: number; current: number }) {
  if (low == null || high == null || high <= low) return <div className="muted-copy">Range data unavailable</div>;
  const pct = Math.max(0, Math.min(100, ((current - low) / (high - low)) * 100));
  return (
    <div className="w-full h-3 rounded-md relative" style={{ background: "var(--surface-2)" }}>
      <div
        className="absolute left-0 top-0 h-full rounded-md"
        style={{ width: `${pct}%`, background: "linear-gradient(90deg, var(--negative) 0%, var(--positive) 100%)" }}
      />
      <div className="absolute top-0" style={{ left: `${pct}%`, transform: "translateX(-50%) translateY(-6px)" }}>
        <div style={{ width: 10, height: 10, borderRadius: 8, background: "#ffffff", border: "2px solid var(--surface)" }} />
      </div>
      <div className="flex justify-between mt-2 text-xs muted-copy" style={{ marginTop: 8 }}>
        <span>{low.toFixed(2)}</span>
        <span>{high.toFixed(2)}</span>
      </div>
    </div>
  );
}

function formatMarketCap(value?: number | null) {
  if (value == null || Number.isNaN(value)) return "-";
  const abs = Math.abs(value);
  if (abs >= 1e9) {
    return `₹${(value / 1e9).toFixed(2)}B`;
  }
  // show in crores
  return `₹${(value / 1e7).toFixed(2)}Cr`;
}

function buildRankContext(row: CandidateRow) {
  if (row.rank === null) {
    return "This name is outside the ranked BUY/WATCH list, so it should be treated as lower priority until the next scan improves.";
  }
  if (row.signal === "BUY") {
    return `This stock is ranked #${row.rank} because its technical quality, trade plan, and supporting evidence place it above the rest of the shortlist.`;
  }
  if (row.signal === "WATCH") {
    return `This stock still has rank #${row.rank}, but the recommendation layer prefers waiting for cleaner confirmation before promoting it to BUY.`;
  }
  return `This stock was shortlisted but fell below the final quality bar, so it remains lower in the decision stack despite passing earlier scan stages.`;
}

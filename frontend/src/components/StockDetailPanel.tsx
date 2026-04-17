import { useState } from "react";
import {
  Bar,
  CartesianGrid,
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
} from "../types";

type StockDetailPanelProps = {
  row: CandidateRow | null;
  onBack?: () => void;
  onSendToPaperTrading?: (row: CandidateRow) => void;
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
          <button type="button" className="button primary-button" onClick={() => onSendToPaperTrading(row)}>
            Send To Paper Trading
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
          <OverviewTab analysis={analysis} row={row} rankReason={rankReason} />
        ) : null}
        {tab === "technicals" ? (
          <TechnicalsTab technical={technical} row={row} />
        ) : null}
        {tab === "trade-plan" ? (
          <TradePlanTab plan={plan} row={row} riskAmount={riskAmount} onRiskAmountChange={setRiskAmount} />
        ) : null}
        {tab === "news" ? (
          <NewsTab analysis={analysis} row={row} />
        ) : null}
        {tab === "backtest" ? (
          <BacktestTab backtest={backtest} />
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
}: {
  analysis?: StockAnalysisResult;
  row: CandidateRow;
  rankReason: string;
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
}: {
  technical?: StockAnalysisResult["technical"][number];
  row: CandidateRow;
}) {
  const indicators = technical?.indicators ?? {};
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
        Source {String(quality.source ?? analysis?.data_source ?? "unknown")} | candles {String(quality.candles ?? "--")} | latest {String(quality.latest_timestamp ?? "--")}
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
}: {
  plan?: TradePlan;
  row: CandidateRow;
  riskAmount: number;
  onRiskAmountChange: (value: number) => void;
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

function NewsTab({ analysis, row }: { analysis?: StockAnalysisResult; row: CandidateRow }) {
  const articles = analysis?.news_articles.slice(0, 3) ?? [];
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
            <p>No article set was returned for this stock.</p>
          </div>
        )}
      </section>
    </div>
  );
}

function BacktestTab({ backtest }: { backtest?: BacktestResult }) {
  if (!backtest) {
    return (
      <section className="subpanel">
        <h3>No backtest support</h3>
        <p>This stock did not return a swing backtest result, so the recommendation is relying more heavily on scanner and technical evidence.</p>
      </section>
    );
  }

  return (
    <div className="detail-stack">
      <section className="detail-grid">
        <div className="subpanel">
          <h3>Backtest strength</h3>
          <div className="score-breakdown">
            <MetricTile label="Win rate" value={`${backtest.win_rate.toFixed(1)}%`} help="Share of historical winning trades." />
            <MetricTile label="Average return" value={`${backtest.total_return.toFixed(1)}%`} help="Total return in the backtest window." />
            <MetricTile label="Max drawdown" value={`${backtest.max_drawdown.toFixed(1)}%`} help="Worst peak-to-trough decline." />
            <MetricTile label="Total trades" value={backtest.trade_count} help="Sample size of historical trades." />
          </div>
          <p className="helper-text">
            <abbr title="Backtest strength summarizes how healthy the historical strategy profile looks.">Backtest strength</abbr>: {backtest.verdict}.
          </p>
        </div>

        <div className="subpanel chart-shell">
          <h3>Equity curve</h3>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={backtest.equity_curve}>
              <CartesianGrid strokeDasharray="2 2" vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} />
              <Tooltip />
              <Bar dataKey="equity" fill="var(--accent-strong)" radius={[4, 4, 0, 0]} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}

function ChartTab({ analysis, plan }: { analysis?: StockAnalysisResult; plan?: TradePlan }) {
  if (!analysis?.ohlcv.length) {
    return (
      <section className="subpanel">
        <h3>Chart unavailable</h3>
        <p>No candle series was returned for this stock.</p>
      </section>
    );
  }

  return (
    <div className="detail-stack">
      <section className="subpanel">
        <h3>Price structure</h3>
        <p className="helper-text">Candles, EMA 20, Supertrend approximation, volume bars, and trade levels are shown together for a practical swing review.</p>
      </section>
      <CandlestickChart candles={analysis.ohlcv.slice(-40)} plan={plan} />
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

  const ema20 = calculateEmaSeries(candles, 20);
  const supertrend = calculateApproxSupertrend(candles, 10, 3);

  const xFor = (index: number) => 30 + (index * (width - 60)) / Math.max(candles.length - 1, 1);
  const yFor = (price: number) => chartTop + ((maxPrice - price) / (maxPrice - minPrice)) * chartHeight;

  const emaPath = buildPath(ema20, xFor, yFor);
  const supertrendPath = buildPath(supertrend, xFor, yFor);
  const tradeLevels = [
    { label: "Entry", value: plan ? (plan.entry_low + plan.entry_high) / 2 : null, className: "chart-line-entry" },
    { label: "Stop", value: plan?.stop_loss ?? null, className: "chart-line-stop" },
    { label: "T1", value: plan?.target_1 ?? null, className: "chart-line-target" },
    { label: "T2", value: plan?.target_2 ?? null, className: "chart-line-target" },
  ].filter((item) => item.value !== null) as { label: string; value: number; className: string }[];

  return (
    <div className="subpanel chart-shell">
      <svg viewBox={`0 0 ${width} ${height}`} className="price-chart" role="img" aria-label="Swing candlestick chart">
        <rect x="0" y="0" width={width} height={height} fill="transparent" />
        {tradeLevels.map((level) => {
          const y = yFor(level.value);
          return (
            <g key={`${level.label}-${level.value}`}>
              <line x1="20" x2={width - 20} y1={y} y2={y} className={level.className} />
              <text x={width - 16} y={y - 4} className="chart-label">
                {level.label} {level.value.toFixed(2)}
              </text>
            </g>
          );
        })}
        <path d={emaPath} className="chart-line-ema" />
        <path d={supertrendPath} className="chart-line-supertrend" />
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
      </svg>
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

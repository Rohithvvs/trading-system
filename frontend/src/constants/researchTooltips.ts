/** Explanation mode: What / Why / How for swing research metrics. */
export const RESEARCH_TOOLTIPS = {
  ai_research_summary: {
    what: "An LLM-written overview of the company and setup, grounded only in available market data.",
    why: "Gives context before you dig into indicators so you understand the business and bias.",
    how: "Read stance and risks first; verify every number against the metric cards below. Never trade on narrative alone.",
  },
  swing_score: {
    what: "A 0–100 composite of trend, momentum, volume, risk, fundamentals, relative strength, volatility, and AI confidence.",
    why: "Collapses multi-factor research into one comparable quality score for swing setups.",
    how: "Prefer higher scores with checklist support. Treat mid scores as watchlist, not auto-buy.",
  },
  company_overview: {
    what: "Description of what the company does and its sector/industry classification.",
    why: "Swing trades still need business context for gap risk and news sensitivity.",
    how: "Avoid names you cannot explain. Flag sectors with event risk (earnings, policy).",
  },
  trend_analysis: {
    what: "Direction and quality of the prevailing price trend using EMAs, ADX, and cross signals.",
    why: "Swing trading profits most from trading with the dominant trend.",
    how: "Favour long setups only in Bullish / Strong Bullish with constructive EMA alignment.",
  },
  ema: {
    what: "Exponential moving averages that weight recent prices more heavily.",
    why: "Show dynamic support/resistance and trend stack health.",
    how: "Price above rising EMA stack supports longs; death cross or price under 200 EMA cautions new longs.",
  },
  adx: {
    what: "Average Directional Index measuring trend strength (not direction).",
    why: "Strong ADX means trends are more tradeable; weak ADX often means chop.",
    how: "ADX above ~25 supports trend-following swings; below ~15 favour mean-reversion or wait.",
  },
  supply_demand: {
    what: "Automatically estimated demand/supply zones, support, resistance, and liquidity areas.",
    why: "Swings often reverse or stall at these levels.",
    how: "Plan entries near demand with stops beyond invalidation; avoid chasing into heavy supply.",
  },
  momentum: {
    what: "Speed and health of the move via RSI, MACD, Stoch RSI, CCI, ROC, and momentum.",
    why: "Trend without momentum often fails; extreme momentum can mean exhaustion.",
    how: "Prefer improving MACD histogram and RSI mid-range (roughly 50–70) for long swings.",
  },
  rsi: {
    what: "Relative Strength Index (14) on a 0–100 scale.",
    why: "Helps gauge overbought/oversold and bullish momentum support.",
    how: "For swings, RSI > 50 with rising trend is constructive; >70 needs tighter risk.",
  },
  macd: {
    what: "Moving Average Convergence Divergence and its signal/histogram.",
    why: "Tracks momentum shifts and trend confirmations.",
    how: "Positive histogram with price in uptrend supports continuation; negative histogram warns of fade.",
  },
  volume: {
    what: "Participation metrics: current vs average volume, OBV trend, breakout flags.",
    why: "Volume validates whether a move has real interest.",
    how: "Prefer breakouts or pullbacks with expanding or accumulation volume.",
  },
  obv: {
    what: "On-Balance Volume cumulative flow of volume on up vs down days.",
    why: "Divergences can foreshadow reversals or confirm accumulation.",
    how: "Rising OBV with rising price is constructive; falling OBV on rallies is a warning.",
  },
  volatility: {
    what: "ATR, Bollinger width, and expected near-term swing range.",
    why: "Sets stop distance and position size realistically.",
    how: "Size positions so stop distance fits risk budget; avoid tiny stops in high ATR names.",
  },
  atr: {
    what: "Average True Range — typical daily movement.",
    why: "Core input for stops, targets, and holding expectations.",
    how: "Place stops beyond ~1 ATR noise; targets often 1.5–3× ATR for swings.",
  },
  price_action: {
    what: "Detected candlestick and structure events (HH/HL, engulfing, gaps, etc.).",
    why: "Confirms or rejects entries at key levels.",
    how: "Use as confirmation with trend/volume — not standalone signals.",
  },
  patterns: {
    what: "Heuristic chart patterns with confidence, target, and invalidation.",
    why: "Classic patterns frame asymmetric risk/reward maps.",
    how: "Trade only high-confidence patterns aligned with higher-timeframe trend; honour invalidation.",
  },
  multi_timeframe: {
    what: "Daily, weekly, and monthly trend/momentum/structure snapshot.",
    why: "Avoid fighting higher-timeframe bias.",
    how: "Best long swings: weekly/monthly constructive, daily trigger pullback or breakout.",
  },
  risk_analysis: {
    what: "Suggested entry, stop, targets, R:R, and position sizing from the research engine.",
    why: "Defines downside before upside.",
    how: "Never enter without a stop. Prefer R:R ≥ 2 when setup quality is only moderate.",
  },
  risk_reward: {
    what: "Potential reward to first target divided by risk to stop.",
    why: "Even 50% win-rate systems need positive expectancy.",
    how: "Skip trades under ~1.5 R:R unless win probability is historically high.",
  },
  holding_period: {
    what: "Estimated swing hold duration and heuristic target probabilities by horizon.",
    why: "Matches capital and attention to trade style.",
    how: "If your max hold is 5 days, avoid setups whose expected hold is 20 days.",
  },
  backtesting: {
    what: "Historical performance of the same swing strategy over last 50/100/250 signals.",
    why: "Validates whether the edge existed historically for this symbol.",
    how: "Demand adequate sample size; low trade count → treat results as weak evidence.",
  },
  similar_setups: {
    what: "Stats for historical signals under the same strategy rules.",
    why: "Answers how often this kind of setup worked before.",
    how: "Compare win rate, median return, and max drawdown before sizing up.",
  },
  ai_confidence: {
    what: "High/Medium/Low label plus explanation of why the recommendation was formed.",
    why: "Transparency into model reasoning.",
    how: "If reasons disagree with your chart read, pass. AI is advisory only.",
  },
  news: {
    what: "Recent headlines classified Positive/Negative/Neutral with impact and rationale.",
    why: "News can gap prices through technical levels.",
    how: "Reduce size into high-impact events; avoid new swings into uncertain headlines.",
  },
  sentiment: {
    what: "Composite of available sentiment sources (news, social, mood, analysts when present).",
    why: "Crowding and narrative risk affect swing follow-through.",
    how: "Treat missing sources as unknown risk, not neutral confirmation.",
  },
  fundamentals: {
    what: "Core valuation and quality metrics from available fundamental feeds.",
    why: "Weak balance sheets raise gap and drawdown risk on multi-day holds.",
    how: "For multi-week swings, avoid extreme debt or collapsing growth unless purely technical scalp.",
  },
  institutional: {
    what: "Institutional and promoter activity when a data feed provides it.",
    why: "Large holders can drive multi-day moves.",
    how: "If data is unavailable, do not invent a view — size more conservatively.",
  },
  checklist: {
    what: "Pass/fail gates across trend, volume, momentum, pattern, fundamentals, risk, reward, AI confidence.",
    why: "Forces process discipline before clicking buy.",
    how: "Require most boxes green for Trade Ready; otherwise Avoid or wait.",
  },
  llm_insights: {
    what: "Professional notes generated only from computed facts.",
    why: "Educates and summarizes without replacing risk rules.",
    how: "Cross-check any number against raw metric cards; report issues if text invents data.",
  },
} as const;

export type ResearchTooltipId = keyof typeof RESEARCH_TOOLTIPS;

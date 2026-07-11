import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  AreaSeries,
  HistogramSeries,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type LineData,
  type HistogramData,
  type Time,
  type SeriesType,
} from "lightweight-charts";
import { fetchChartData, saveChartLayout, type ChartDataResponse } from "../../api_retail";
import { ProfessionalOrderTicket } from "../../components/retail/ProfessionalOrderTicket";
import { useTheme } from "../../hooks/useTheme";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"] as const;
const CHART_TYPES = ["candlestick", "line", "area"] as const;
const INDICATORS = ["EMA", "SMA", "VWAP", "RSI", "MACD", "ATR", "Supertrend", "Bollinger"] as const;

type Tab = { id: string; symbol: string; timeframe: string };

export function ChartWorkspacePage() {
  const { symbol: routeSymbol } = useParams();
  const navigate = useNavigate();
  const { theme } = useTheme();
  const [tabs, setTabs] = useState<Tab[]>([{ id: "1", symbol: (routeSymbol || "RELIANCE").toUpperCase(), timeframe: "1D" }]);
  const [activeTab, setActiveTab] = useState("1");
  const [chartType, setChartType] = useState<(typeof CHART_TYPES)[number]>("candlestick");
  const [enabledInd, setEnabledInd] = useState<string[]>(["EMA", "SMA", "VWAP"]);
  const [drawTool, setDrawTool] = useState<string | null>(null);
  const [drawings, setDrawings] = useState<{ type: string; points: { x: number; y: number }[] }[]>([]);
  const [fullscreen, setFullscreen] = useState(false);
  const [data, setData] = useState<ChartDataResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const overlayLinesRef = useRef<ISeriesApi<"Line">[]>([]);

  const tab = tabs.find((t) => t.id === activeTab) || tabs[0];

  useEffect(() => {
    if (routeSymbol) {
      const sym = routeSymbol.toUpperCase();
      setTabs((prev) => {
        const exists = prev.find((t) => t.id === activeTab);
        if (exists && exists.symbol === sym) return prev;
        return prev.map((t) => (t.id === activeTab ? { ...t, symbol: sym } : t));
      });
    }
  }, [routeSymbol, activeTab]);

  useEffect(() => {
    if (!tab) return;
    setLoading(true);
    setError(null);
    void fetchChartData(tab.symbol, tab.timeframe, enabledInd.join(","))
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [tab?.symbol, tab?.timeframe, enabledInd]);

  useEffect(() => {
    if (!containerRef.current) return;
    const isDark = theme === "dark";
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: isDark ? "#151a21" : "#ffffff" },
        textColor: isDark ? "#9eacbb" : "#5b6777",
      },
      grid: {
        vertLines: { color: isDark ? "#222b36" : "#eef2f7" },
        horzLines: { color: isDark ? "#222b36" : "#eef2f7" },
      },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: isDark ? "#2c3745" : "#d9e1ea" },
      timeScale: { borderColor: isDark ? "#2c3745" : "#d9e1ea", timeVisible: true },
    });
    chartRef.current = chart;

    const vol = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: "rgba(46,139,218,0.4)",
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volumeRef.current = vol;

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      volumeRef.current = null;
      overlayLinesRef.current = [];
    };
  }, [theme, fullscreen]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !data) return;

    for (const s of overlayLinesRef.current) {
      try {
        chart.removeSeries(s);
      } catch {
        /* ignore */
      }
    }
    overlayLinesRef.current = [];

    if (seriesRef.current) {
      try {
        chart.removeSeries(seriesRef.current);
      } catch {
        /* ignore */
      }
      seriesRef.current = null;
    }

    const candles = data.candles.map((c) => ({
      time: c.time as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    })) as CandlestickData[];

    if (chartType === "candlestick") {
      const s = chart.addSeries(CandlestickSeries, {
        upColor: "#38b26d",
        downColor: "#c05c54",
        borderVisible: false,
        wickUpColor: "#38b26d",
        wickDownColor: "#c05c54",
      });
      s.setData(candles);
      seriesRef.current = s;
    } else if (chartType === "line") {
      const s = chart.addSeries(LineSeries, { color: "#2e8bda", lineWidth: 2 });
      s.setData(candles.map((c) => ({ time: c.time, value: c.close })) as LineData[]);
      seriesRef.current = s;
    } else {
      const s = chart.addSeries(AreaSeries, {
        lineColor: "#2e8bda",
        topColor: "rgba(46,139,218,0.35)",
        bottomColor: "rgba(46,139,218,0.02)",
      });
      s.setData(candles.map((c) => ({ time: c.time, value: c.close })) as LineData[]);
      seriesRef.current = s;
    }

    volumeRef.current?.setData(
      data.candles.map((c) => ({
        time: c.time as Time,
        value: c.volume,
        color: c.close >= c.open ? "rgba(56,178,109,0.4)" : "rgba(192,92,84,0.4)",
      })) as HistogramData[],
    );

    const lineColors: Record<string, string> = {
      ema20: "#f59e0b",
      ema50: "#8b5cf6",
      sma20: "#06b6d4",
      sma50: "#ec4899",
      vwap: "#14b8a6",
      supertrend: "#22c55e",
      bb_upper: "#94a3b8",
      bb_mid: "#64748b",
      bb_lower: "#94a3b8",
    };
    for (const [key, color] of Object.entries(lineColors)) {
      const pts = data.indicators[key] as { time: number; value: number }[] | undefined;
      if (!pts?.length) continue;
      const ls = chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      ls.setData(pts.map((p) => ({ time: p.time as Time, value: p.value })));
      overlayLinesRef.current.push(ls);
    }

    chart.timeScale().fitContent();
  }, [data, chartType]);

  function addTab() {
    const id = String(Date.now());
    setTabs((t) => [...t, { id, symbol: tab?.symbol || "RELIANCE", timeframe: "1D" }]);
    setActiveTab(id);
  }

  function toggleInd(name: string) {
    setEnabledInd((prev) => (prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]));
  }

  async function autosave() {
    if (!tab) return;
    try {
      await saveChartLayout({
        name: `${tab.symbol}-${tab.timeframe}-autosave`,
        symbol: tab.symbol,
        timeframe: tab.timeframe,
        chart_type: chartType,
        theme,
        indicators: enabledInd.map((n) => ({ name: n })),
        drawings,
        is_default: false,
      });
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    const id = setInterval(() => void autosave(), 60000);
    return () => clearInterval(id);
  });

  return (
    <div className={`chart-workspace ${fullscreen ? "is-fullscreen" : ""}`}>
      <div className="chart-tabs">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`chart-tab ${t.id === activeTab ? "is-active" : ""}`}
            onClick={() => {
              setActiveTab(t.id);
              navigate(`/chart/${t.symbol}`);
            }}
          >
            {t.symbol}
            {tabs.length > 1 ? (
              <span
                className="tab-close"
                onClick={(e) => {
                  e.stopPropagation();
                  const next = tabs.filter((x) => x.id !== t.id);
                  setTabs(next);
                  if (activeTab === t.id) setActiveTab(next[0]?.id || "1");
                }}
              >
                ×
              </span>
            ) : null}
          </button>
        ))}
        <button type="button" className="chart-tab" onClick={addTab}>+</button>
      </div>

      <div className="chart-toolbar">
        <div className="tf-group">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              type="button"
              className={tab?.timeframe === tf ? "is-active" : ""}
              onClick={() => setTabs((prev) => prev.map((t) => (t.id === activeTab ? { ...t, timeframe: tf } : t)))}
            >
              {tf}
            </button>
          ))}
        </div>
        <div className="tf-group">
          {CHART_TYPES.map((ct) => (
            <button key={ct} type="button" className={chartType === ct ? "is-active" : ""} onClick={() => setChartType(ct)}>
              {ct}
            </button>
          ))}
        </div>
        <div className="tf-group">
          {INDICATORS.map((ind) => (
            <button key={ind} type="button" className={enabledInd.includes(ind) ? "is-active" : ""} onClick={() => toggleInd(ind)}>
              {ind}
            </button>
          ))}
        </div>
        <div className="tf-group">
          {["Trendline", "Horizontal", "Vertical", "Rectangle", "Fib", "Ray", "Crosshair"].map((tool) => (
            <button
              key={tool}
              type="button"
              className={drawTool === tool ? "is-active" : ""}
              onClick={() => setDrawTool((t) => (t === tool ? null : tool))}
            >
              {tool}
            </button>
          ))}
        </div>
        <button type="button" className="button ghost-button" onClick={() => setFullscreen((f) => !f)}>
          {fullscreen ? "Exit fullscreen" : "Fullscreen"}
        </button>
        <button type="button" className="button ghost-button" onClick={() => void autosave()}>
          Save layout
        </button>
      </div>

      <div className="chart-body">
        <div className="chart-main">
          {loading ? <div className="muted-copy" style={{ padding: 8 }}>Loading chart…</div> : null}
          {error ? <div className="warning-box">{error}</div> : null}
          <div className="chart-canvas-wrap" style={{ position: "relative", height: fullscreen ? "80vh" : 480 }}>
            <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
            <div
              className="chart-draw-overlay"
              style={{ position: "absolute", inset: 0, pointerEvents: drawTool ? "auto" : "none" }}
              onClick={(e) => {
                if (!drawTool) return;
                const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect();
                const pt = { x: e.clientX - rect.left, y: e.clientY - rect.top };
                setDrawings((d) => {
                  const last = d[d.length - 1];
                  if (last && last.points.length < 2) {
                    return [...d.slice(0, -1), { ...last, points: [...last.points, pt] }];
                  }
                  return [...d, { type: drawTool, points: [pt] }];
                });
              }}
            />
          </div>
          <div className="muted-copy" style={{ padding: "4px 8px" }}>
            {data ? `${data.symbol} · ${data.timeframe} · ${data.candles.length} bars · source ${data.source}` : "No data"}
            {drawings.length ? ` · ${drawings.length} drawings` : ""}
          </div>
        </div>
        <div className="chart-side">
          <ProfessionalOrderTicket symbol={tab?.symbol} />
        </div>
      </div>
    </div>
  );
}

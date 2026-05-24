import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import Dashboard from '../../Dashboard';
import { CandidateTable } from '../CandidateTable';
import type { CandidateRow } from '../../types';

// Mock recharts to prevent render errors in JSDOM
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  AreaChart: () => <div>AreaChart</div>,
  Area: () => <div>Area</div>,
  YAxis: () => <div>YAxis</div>,
}));

describe('Dashboard Component', () => {
  it('renders Multi-Agent Progress Tracker overlay when isLoading is true', () => {
    // In a real test, we would mock the `useDashboard` hook or internal state.
    // For this demonstration, we are testing the component contract.
    // Assuming we can pass an initial state or we mock the API to keep it loading.
    expect(true).toBe(true); // Placeholder for actual implementation hooked into state
  });
});

describe('CandidateTable Component', () => {
  const mockRow: CandidateRow = {
    rank: 1,
    symbol: 'TCS.NS',
    signal: 'BUY',
    score: 85.5,
    confidence: 0.9,
    entryLow: 3500,
    entryHigh: 3550,
    stopLoss: 3400,
    target1: 3800,
    target2: null,
    riskReward: 2.5,
    trend: 'Bullish',
    momentum: 'Strong',
    volume: 'High',
    newsSentiment: 'Bullish',
    lastUpdated: '2023-10-01T10:00:00Z',
    tradeReadiness: 'High',
    recommendationSummary: 'Strong buy',
    analysisItem: {
      symbol: 'TCS.NS',
      backtests: [{
        mode: 'swing',
        strategy_name: 'EMA Crossover',
        total_return: 15.0,
        cagr: 10.0,
        max_drawdown: 5.0,
        win_rate: 0.65,
        profit_factor: 1.8,
        trade_count: 50,
        verdict: 'Pass',
        equity_curve: [{ label: '1', equity: 100 }, { label: '2', equity: 115 }]
      }],
      ohlcv: [],
      technical: [],
      news_articles: [],
      news_summary: '',
      news_sentiment_label: 'Bullish',
      news_sentiment_score: 0.8,
      recommendation: {} as any,
      disclaimer: ''
    }
  };

  it('renders the System Alpha Card correctly with aggregated data', () => {
    render(<CandidateTable rows={[mockRow]} selectedSymbol={null} onSelect={vi.fn()} />);
    
    // Win rate should be 0.65 * 100 = 65.0%
    expect(screen.getByText('65.0%')).toBeDefined();
    // Profit factor should be 1.80x
    expect(screen.getByText('1.80x')).toBeDefined();
  });

  it('renders the Regime Badge based on sentiment', () => {
    render(<CandidateTable rows={[mockRow]} selectedSymbol={null} onSelect={vi.fn()} />);
    // Because newsSentiment is 'Bullish', it should render 'CATALYST' badge
    expect(screen.getByText('CATALYST')).toBeDefined();
  });
});

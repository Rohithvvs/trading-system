import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { MarketEngineHealthWidget } from '../PaperTradingPage';
import { MarketEngineHealth } from '../../types';

describe('MarketEngineHealthWidget', () => {
  const mockHealth: MarketEngineHealth = {
    status: 'RUNNING',
    last_tick_at: new Date().toISOString(),
    last_reconciliation_at: new Date().toISOString(),
    open_positions: 5,
    tracked_symbols: 10,
  };

  it('renders RUNNING state successfully', () => {
    render(<MarketEngineHealthWidget health={mockHealth} lastSuccessfulPoll={Date.now()} errorCount={0} />);
    expect(screen.getByText(/🟢 RUNNING/)).toBeDefined();
  });

  it('renders DEGRADED state with stale data warning when error count is high', () => {
    // 4 errors = 40 seconds elapsed > 30 seconds
    render(<MarketEngineHealthWidget health={mockHealth} lastSuccessfulPoll={Date.now()} errorCount={4} />);
    expect(screen.getByText(/🟡 DEGRADED/)).toBeDefined();
    expect(screen.getByText(/⚠ Data may be stale/)).toBeDefined();
  });

  it('renders DEGRADED state without stale warning when error count is low', () => {
    // 1 error = 10 seconds elapsed <= 30 seconds
    render(<MarketEngineHealthWidget health={mockHealth} lastSuccessfulPoll={Date.now()} errorCount={1} />);
    expect(screen.getByText(/🟡 DEGRADED/)).toBeDefined();
    expect(screen.queryByText(/⚠ Data may be stale/)).toBeNull();
  });

  it('returns null if health is null and errorCount is 0 (initial load)', () => {
    const { container } = render(<MarketEngineHealthWidget health={null} lastSuccessfulPoll={null} errorCount={0} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders UNKNOWN/DEGRADED state if health is null but errorCount is > 0', () => {
    render(<MarketEngineHealthWidget health={null} lastSuccessfulPoll={null} errorCount={1} />);
    expect(screen.getByText(/🟡 DEGRADED/)).toBeDefined();
  });
});


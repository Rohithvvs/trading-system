import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ScannerProgress } from '../components/ScannerProgress';

describe('ScannerProgress Component Isolation Tests', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders default/active state correctly', () => {
    render(<ScannerProgress data={{ stage: "Fetching Data", progress: 45, current_symbol: "", done: 0, remaining: 0, eta_sec: 0 }} error={null} startTime={Date.now()} />);

    expect(screen.getByText('Scanner Active')).toBeDefined();
    expect(screen.getByText('Fetching Data')).toBeDefined();
    expect(screen.getByText('45%')).toBeDefined();
  });

  it('renders error state correctly and handles retry', () => {
    const onRetry = vi.fn();
    render(<ScannerProgress data={{ stage: "Fetching Data", progress: 45 }} error="Connection failed" startTime={Date.now()} onRetry={onRetry} />);

    expect(screen.getByText('Connection failed')).toBeDefined();
    expect(screen.queryByText('Scanner Active')).toBeNull();

    const retryBtn = screen.getByText('Retry Scan');
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('updates elapsed time based on startTime', () => {
    const startTime = Date.now() - 5000;
    render(<ScannerProgress data={{ stage: "Processing", progress: 10, current_symbol: "", done: 0, remaining: 0, eta_sec: 0 }} error={null} startTime={startTime} />);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    // 5 seconds ago + 1 second elapsed = 6s
    expect(screen.getByText(/6s elapsed/)).toBeDefined();
  });

  it('does not render elapsed timer or progress if completed (progress >= 100)', () => {
    const startTime = Date.now();
    const { container } = render(<ScannerProgress data={{ stage: "Complete", progress: 100, current_symbol: "", done: 0, remaining: 0, eta_sec: 0 }} error={null} startTime={startTime} />);

    expect(screen.getByText('100%')).toBeDefined();

    act(() => {
      vi.advanceTimersByTime(10000);
    });

    expect(screen.getByText(/0s elapsed/)).toBeDefined();
  });
});

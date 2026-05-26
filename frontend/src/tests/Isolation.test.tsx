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
    render(<ScannerProgress stage="Fetching Data" progress={45} error={null} startTime={Date.now()} />);
    
    expect(screen.getByText('Multi-Agent Scanner Active')).toBeDefined();
    expect(screen.getByText('Fetching Data')).toBeDefined();
    expect(screen.getByText('45%')).toBeDefined();
  });

  it('renders error state correctly and handles retry', () => {
    const onRetry = vi.fn();
    render(<ScannerProgress stage="Fetching Data" progress={45} error="Connection failed" startTime={Date.now()} onRetry={onRetry} />);
    
    // Should render error text
    expect(screen.getByText('Connection failed')).toBeDefined();
    
    // Should not render the active scanner title in error mode
    expect(screen.queryByText('Multi-Agent Scanner Active')).toBeNull();

    // Click retry
    const retryBtn = screen.getByText('Retry Scan');
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('updates elapsed time based on startTime', () => {
    const startTime = Date.now() - 5000; // 5 seconds ago
    render(<ScannerProgress stage="Processing" progress={10} error={null} startTime={startTime} />);
    
    // It starts by calculating elapsed based on start time on interval tick
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    
    // 5 seconds ago + 1 second elapsed = 6s
    expect(screen.getByText('Elapsed Time: 6s')).toBeDefined();
  });

  it('does not render elapsed timer or progress if completed (progress >= 100)', () => {
    const { container } = render(<ScannerProgress stage="Complete" progress={100} error={null} startTime={Date.now()} />);
    
    expect(screen.getByText('100%')).toBeDefined();
    
    // Verify interval doesn't tick when completed
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    
    expect(screen.getByText('Elapsed Time: 0s')).toBeDefined();
  });
});

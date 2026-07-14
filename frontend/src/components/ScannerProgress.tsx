import { useEffect, useState } from "react";

interface ScannerProgressData {
  stage: string;
  progress: number;
  current_symbol?: string;
  worker_id?: number;
  done?: number;
  remaining?: number;
  total_fetch?: number;
  total_scoring?: number;
  eta_sec?: number;
}

interface ScannerProgressProps {
  data: ScannerProgressData;
  error: string | null;
  onRetry?: () => void;
  startTime: number | null;
}

function formatEta(seconds: number | undefined): string {
  if (seconds == null || seconds <= 0) return "--";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}s`;
}

export function ScannerProgress({ data, error, onRetry, startTime }: ScannerProgressProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!startTime || error || data.progress >= 100) return;
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime, error, data.progress]);

  if (error) {
    return (
      <div className="scanner-progress scanner-progress--error" role="alert">
        <div className="scanner-progress__error-content">
          <span className="scanner-progress__error-icon" aria-hidden>🔴</span>
          <span>{error}</span>
        </div>
        {onRetry && (
          <button type="button" className="ds-btn ds-btn--primary" onClick={onRetry}>
            Retry Scan
          </button>
        )}
      </div>
    );
  }

  const pct = Math.min(data.progress, 100);
  const total = data.total_fetch || data.total_scoring || 0;
  const completed = data.done || 0;
  const remaining = data.remaining ?? 0;

  return (
    <div className="scanner-progress">
      <div className="scanner-progress__header">
        <div className="scanner-progress__title">
          <span className="scanner-progress__dot" aria-hidden />
          Scanner Active
        </div>
        <div className="scanner-progress__timing">
          <span className="scanner-progress__elapsed">{formatElapsed(elapsed)} elapsed</span>
          {data.eta_sec != null && data.eta_sec > 0 && (
            <span className="scanner-progress__eta">ETA {formatEta(data.eta_sec)}</span>
          )}
        </div>
      </div>

      <div className="scanner-progress__stage">{data.stage}</div>

      <div className="scanner-progress__bar-track">
        <div
          className="scanner-progress__bar-fill"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="scanner-progress__stats">
        {total > 0 && (
          <span className="scanner-progress__stat">
            {completed} / {total}
          </span>
        )}
        {data.current_symbol && (
          <span className="scanner-progress__stat">
            Current: <strong>{data.current_symbol}</strong>
          </span>
        )}
        {data.worker_id != null && (
          <span className="scanner-progress__stat">
            Worker #{data.worker_id}
          </span>
        )}
        <span className="scanner-progress__stat">
          {pct.toFixed(0)}%
        </span>
      </div>
    </div>
  );
}

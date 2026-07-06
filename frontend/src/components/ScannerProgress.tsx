import { useEffect, useState } from "react";

interface ScannerProgressProps {
  stage: string;
  progress: number;
  error: string | null;
  onRetry?: () => void;
  startTime: number | null;
}

export function ScannerProgress({ stage, progress, error, onRetry, startTime }: ScannerProgressProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!startTime || error || progress >= 100) {
      return;
    }
    
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);
    
    return () => clearInterval(interval);
  }, [startTime, error, progress]);

  if (error) {
    return (
      <div style={{
        background: "#fee2e2",
        border: "1px solid #f87171",
        borderRadius: "8px",
        padding: "16px",
        color: "#991b1b",
        fontWeight: 600,
        fontSize: "14px",
        margin: "16px 0",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span>🔴</span>
          <span>{error}</span>
        </div>
        {onRetry && (
          <div>
            <button type="button" className="button primary-button" onClick={onRetry}>
              Retry Scan
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="agent-tracker-overlay">
      <div className="agent-tracker-card" style={{ maxWidth: "500px", margin: "0 auto", padding: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "16px" }}>
          <h2><span className="pulsing-dot"></span> Multi-Agent Scanner Active</h2>
          <span style={{ fontSize: "14px", color: "var(--color-text-dim)" }}>
            Elapsed Time: {elapsed}s
          </span>
        </div>
        
        <p className="agent-tracker-subtitle" style={{ fontSize: "16px", fontWeight: "600", marginBottom: "8px" }}>
          {stage.includes("Waking") || stage.includes("backend") ? "⏳ Starting backend on Render..." : stage}
        </p>
        {(stage.includes("Waking") || stage.includes("backend")) && (
          <p style={{ fontSize: "13px", color: "#666", marginBottom: "12px" }}>
            This may take up to 60 seconds on free Render tier. Please wait...
          </p>
        )}
        
        <div style={{ width: "100%", height: "8px", background: "var(--color-border)", borderRadius: "4px", overflow: "hidden", marginBottom: "8px" }}>
          <div 
            style={{ 
              width: `${progress}%`, 
              height: "100%", 
              background: "var(--color-primary)", 
              transition: "width 0.3s ease-out" 
            }} 
          />
        </div>
        
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <span style={{ fontSize: "14px", fontWeight: "600", color: "var(--color-primary)" }}>
            {progress}%
          </span>
        </div>
      </div>
    </div>
  );
}

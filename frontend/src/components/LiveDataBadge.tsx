import React, { useEffect, useState } from "react";

type WsStatus = "connecting" | "connected" | "disconnected";

interface LiveDataBadgeProps {
  status: WsStatus;
  lastMessageAt: Date | null;
}

export default function LiveDataBadge({ status, lastMessageAt }: LiveDataBadgeProps) {
  const [pulseKey, setPulseKey] = useState(0);

  // Trigger a re-render/animation key reset whenever lastMessageAt changes
  useEffect(() => {
    if (lastMessageAt) {
      setPulseKey(prev => prev + 1);
    }
  }, [lastMessageAt]);

  const isConnected = status === "connected";
  
  let badgeText = "Connecting...";
  let badgeClass = "live-badge ";

  if (status === "connecting") {
    badgeClass += "connecting";
    badgeText = "Connecting...";
  } else if (status === "disconnected") {
    badgeClass += "disconnected";
    badgeText = "Disconnected";
  } else if (status === "connected") {
    badgeClass += "connected";
    badgeText = "LIVE DATA";
  }

  return (
    <div className="live-badge-container" title={lastMessageAt ? `Last tick: ${lastMessageAt.toLocaleTimeString()}` : "No data yet"}>
      <div className={badgeClass}>
        <div 
          key={pulseKey} 
          className={`live-badge-dot ${isConnected && lastMessageAt ? "ping" : ""}`} 
        />
        {badgeText}
      </div>
    </div>
  );
}

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
  
  // Base classes for the indicator dot
  let dotClasses = "w-2 h-2 rounded-full mr-2 ";
  let badgeText = "Connecting...";
  let badgeClasses = "flex items-center text-xs font-semibold px-2 py-1 rounded border ";

  if (status === "connecting") {
    dotClasses += "bg-yellow-500 animate-pulse";
    badgeClasses += "bg-yellow-100 text-yellow-800 border-yellow-300 dark:bg-yellow-900 dark:text-yellow-200 dark:border-yellow-700";
    badgeText = "Connecting...";
  } else if (status === "disconnected") {
    dotClasses += "bg-gray-500";
    badgeClasses += "bg-gray-100 text-gray-800 border-gray-300 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-600";
    badgeText = "Disconnected";
  } else if (status === "connected") {
    dotClasses += "bg-green-500";
    badgeClasses += "bg-green-100 text-green-800 border-green-300 dark:bg-green-900/40 dark:text-green-300 dark:border-green-800";
    badgeText = "LIVE DATA";
  }

  return (
    <div className="flex items-center" title={lastMessageAt ? `Last tick: ${lastMessageAt.toLocaleTimeString()}` : "No data yet"}>
      <div className={badgeClasses}>
        <div 
          key={pulseKey} 
          className={dotClasses + (isConnected && lastMessageAt ? " animate-[ping_1s_cubic-bezier(0,0,0.2,1)_1]" : "")} 
        />
        {badgeText}
      </div>
    </div>
  );
}

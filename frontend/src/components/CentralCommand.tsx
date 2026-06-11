import React, { useState } from "react";
import { useTradingDashboard } from "../hooks/useTradingDashboard";
import { cancelPaperOrder, placePaperOrder } from "../api";
import type { PaperOrderTicketState, PaperPosition, ScreenerConditionResult } from "../types";

export function CentralCommand() {
  const { engineStatus, accountSummary, recentScans, isDisconnected, isLiveDataActive } = useTradingDashboard();
  const [selectedStock, setSelectedStock] = useState<ScreenerConditionResult | null>(null);

  const handleClosePosition = async (position: PaperPosition) => {
    // API call to close position
    // Usually this is submitting an opposite order or using a specific close endpoint
    // For this example, we'll log it or use placePaperOrder
    console.log("Closing position", position.symbol);
  };

  const handleBuy = async () => {
    if (!selectedStock || !isLiveDataActive) return;
    const ticket: PaperOrderTicketState = {
      symbol: selectedStock.symbol,
      side: "BUY",
      type: "MARKET",
      qty: 10, // Default qty
    };
    try {
      await placePaperOrder(ticket, crypto.randomUUID());
      alert("Order placed successfully");
    } catch (err: any) {
      alert("Order failed: " + err.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans flex flex-col">
      {/* PHASE 2: THE HEADER & DUAL HEARTBEAT */}
      <header className="sticky top-0 z-50 bg-slate-900 border-b border-slate-800 px-6 py-4 flex justify-between items-center shadow-md">
        <div className="flex items-center space-x-6">
          <h1 className="text-xl font-bold text-white tracking-tight">Central Command</h1>
          
          <div className="flex items-center space-x-4 bg-slate-950 px-4 py-2 rounded-lg border border-slate-800">
            {/* System Engine Status */}
            <div className="flex items-center space-x-2">
              <span className={`h-2.5 w-2.5 rounded-full ${engineStatus?.status === 'running' ? 'bg-green-500' : 'bg-red-500'}`}></span>
              <span className="text-sm font-medium text-slate-300">
                Engine: {engineStatus?.status === 'running' ? 'Running' : 'Stopped'}
              </span>
            </div>
            <div className="w-px h-4 bg-slate-700"></div>
            {/* Data Feed Status */}
            <div className="flex items-center space-x-2">
              {isLiveDataActive ? (
                <>
                  <span className="flex h-2.5 w-2.5 relative">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500"></span>
                  </span>
                  <span className="text-sm font-medium text-green-400">Data: Live</span>
                </>
              ) : (
                <>
                  <span className="h-2.5 w-2.5 rounded-full bg-red-500"></span>
                  <span className="text-sm font-medium text-red-500">Data: Offline</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* P&L Metric */}
        <div className="flex items-center space-x-4">
          <div className="bg-slate-950 px-4 py-2 rounded-lg border border-slate-800">
            <span className="text-sm text-slate-400 mr-2">Total P&L:</span>
            <span className={`text-lg font-bold ${accountSummary?.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              {accountSummary?.total_pnl >= 0 ? '+' : ''}₹{accountSummary?.total_pnl?.toFixed(2) || '0.00'}
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 p-6 grid grid-cols-12 gap-6">
        {/* LEFT COLUMN: Portfolio Widget */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
          <section className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm flex-1">
            <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/50">
              <h2 className="text-lg font-semibold text-white">Open Positions</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-300">
                <thead className="bg-slate-950/50 text-slate-400 text-xs uppercase font-medium">
                  <tr>
                    <th className="px-6 py-3">Symbol</th>
                    <th className="px-6 py-3">Side</th>
                    <th className="px-6 py-3">Entry Price</th>
                    <th className="px-6 py-3">Current LTP</th>
                    <th className="px-6 py-3">Unrealized P&L</th>
                    <th className="px-6 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {accountSummary?.positions?.map((pos: PaperPosition, idx: number) => (
                    <tr key={idx} className="hover:bg-slate-800/20 transition-colors">
                      <td className="px-6 py-4 font-medium text-white">{pos.symbol}</td>
                      <td className="px-6 py-4">
                        <span className={`px-2 py-1 rounded text-xs font-bold ${pos.side === 'LONG' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
                          {pos.side}
                        </span>
                      </td>
                      <td className="px-6 py-4">₹{pos.average_price?.toFixed(2)}</td>
                      <td className="px-6 py-4">₹{pos.current_price?.toFixed(2)}</td>
                      <td className={`px-6 py-4 font-medium ${pos.unrealized_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}₹{pos.unrealized_pnl?.toFixed(2)}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={() => handleClosePosition(pos)}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-md transition-colors"
                        >
                          Close Position
                        </button>
                      </td>
                    </tr>
                  ))}
                  {(!accountSummary?.positions || accountSummary.positions.length === 0) && (
                    <tr>
                      <td colSpan={6} className="px-6 py-8 text-center text-slate-500 italic">
                        No open positions.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* PHASE 4: THE ORDER EXECUTION SAFEGUARD (Stock Observation Panel) */}
          {selectedStock && (
            <section className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm p-6 flex flex-col gap-4">
              <h2 className="text-lg font-semibold text-white border-b border-slate-800 pb-2">
                Order Panel: {selectedStock.symbol}
              </h2>
              
              <div className="flex flex-col md:flex-row gap-6">
                <div className="flex-1 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                      <p className="text-xs text-slate-400 mb-1">Signal</p>
                      <p className={`text-lg font-bold ${selectedStock.technical_signal === 'BUY' ? 'text-green-500' : 'text-slate-200'}`}>
                        {selectedStock.technical_signal}
                      </p>
                    </div>
                    <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
                      <p className="text-xs text-slate-400 mb-1">Score</p>
                      <p className="text-lg font-bold text-white">{selectedStock.screener_score}</p>
                    </div>
                  </div>
                </div>

                {/* Buy Order Confirmation Card with Safeguards */}
                <div className={`flex-1 p-5 rounded-xl border transition-colors ${!isLiveDataActive ? 'bg-red-950/20 border-red-900/50' : 'bg-slate-950 border-slate-800'}`}>
                  {/* Visual Status Feedback */}
                  <div className="flex items-center space-x-2 mb-4 pb-3 border-b border-slate-800/50">
                    {isLiveDataActive ? (
                      <>
                        <span className="flex h-3 w-3 relative">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                          <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                        </span>
                        <span className="text-xs font-bold tracking-wider text-green-400">LIVE MARKET SPREAD</span>
                      </>
                    ) : (
                      <>
                        <span className="h-3 w-3 rounded-full bg-red-500 inline-block"></span>
                        <span className="text-xs font-bold tracking-wider text-red-500">STALE DATA — EXECUTION HALTED</span>
                      </>
                    )}
                  </div>

                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-slate-400">Action</span>
                      <span className="text-sm font-bold text-green-400">BUY {selectedStock.symbol}</span>
                    </div>
                    
                    <button
                      onClick={handleBuy}
                      disabled={!isLiveDataActive}
                      className="w-full py-3 px-4 rounded-lg font-bold text-sm transition-all
                               bg-green-600 hover:bg-green-500 text-white shadow-lg shadow-green-900/20
                               disabled:opacity-40 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500 disabled:shadow-none"
                    >
                      Confirm Buy Order
                    </button>
                    
                    {!isLiveDataActive && (
                      <p className="text-xs text-red-400/80 text-center mt-2 italic">
                        Order placement disabled because live feed is offline or rate-limited.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </section>
          )}
        </div>

        {/* RIGHT COLUMN: Live Scanner Feed */}
        <div className="col-span-12 lg:col-span-4">
          <section className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-sm h-full flex flex-col">
            <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
              <h2 className="text-lg font-semibold text-white">Live Scanner Feed</h2>
              <span className="px-2 py-1 bg-blue-500/10 text-blue-400 text-xs font-bold rounded">
                {recentScans.length} Matches
              </span>
            </div>
            
            <div className="flex-1 overflow-y-auto p-4 space-y-3 max-h-[800px]">
              {recentScans.map((scan, idx) => (
                <div 
                  key={idx} 
                  onClick={() => setSelectedStock(scan)}
                  className={`p-4 rounded-lg border cursor-pointer transition-all
                            ${selectedStock?.symbol === scan.symbol ? 'bg-slate-800 border-slate-600 shadow-md' : 'bg-slate-950 border-slate-800 hover:border-slate-700 hover:bg-slate-900'}`}
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="font-bold text-white">{scan.symbol}</h3>
                    <span className={`text-xs font-bold px-2 py-1 rounded ${scan.technical_signal === 'BUY' ? 'bg-green-500/10 text-green-400' : 'bg-yellow-500/10 text-yellow-400'}`}>
                      {scan.technical_signal}
                    </span>
                  </div>
                  <div className="flex justify-between items-center text-xs text-slate-400">
                    <span>Score: <span className="text-white font-medium">{scan.screener_score}</span></span>
                    <span>1D Timeframe</span>
                  </div>
                </div>
              ))}
              {recentScans.length === 0 && (
                <div className="text-center py-8 text-slate-500">
                  <p>No valid stocks found in recent scan.</p>
                </div>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}

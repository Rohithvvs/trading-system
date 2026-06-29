import asyncio
import threading
import sys
import time
import traceback
from app.main import app
from app.schemas.analysis import ScreenerRequest, TimeframeConfig, AnalysisMode
from app.services.scan_execution_service import ScanExecutionService

async def main():
    payload = ScreenerRequest(
        mode=AnalysisMode.swing,
        top_n=20,
        symbols=[],
        timeframe=TimeframeConfig(lookback_window=180, swing="1d")
    )
    
    # Start a thread to dump traces after 5 seconds
    def dumper():
        time.sleep(5)
        print("--- THREAD DUMP ---")
        for thread_id, frame in sys._current_frames().items():
            print(f"Thread ID: {thread_id}")
            traceback.print_stack(frame)
            print("-" * 40)
            
    threading.Thread(target=dumper, daemon=True).start()
    
    print("Starting scan...")
    q = asyncio.Queue()
    await ScanExecutionService.execute_scan(payload, progress_queue=q, trigger_source="ui")
    while True:
        msg = await q.get()
        print("Progress:", msg)
        if "status" in msg and msg["status"] in ("complete", "error"):
            break

if __name__ == "__main__":
    asyncio.run(main())

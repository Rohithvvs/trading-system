import asyncio
import os
import logging
from unittest.mock import patch, MagicMock

os.environ["SCHEDULER_SECRET"] = "test-secret"
os.environ["APP_ENV"] = "test"
os.environ["FYERS_CLIENT_ID"] = "dummy"
os.environ["FYERS_SECRET_KEY"] = "dummy"

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from backend.app.routes.scheduler import router as scheduler_router
from backend.app.schemas import ScreenerResponse
from backend.app.agents import RouterAgent
from backend.app.services.scan_execution_service import ScanExecutionService

app = FastAPI()
app.include_router(scheduler_router)

logging.basicConfig(level=logging.INFO)

async def run_tests():
    transport = ASGITransport(app=app)
    
    print("--- TEST 1: AUTHENTICATION ---")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"mode": "swing"}
        # A. Missing X-Scheduler-Secret
        res = await client.post("/scheduler/daily-scan", json=payload)
        t1_a = res.status_code == 401
        print(f"Missing Secret -> {res.status_code} (Expected 401): {'PASS' if t1_a else 'FAIL'}")

        # B. Invalid Secret
        res = await client.post("/scheduler/daily-scan", json=payload, headers={"X-Scheduler-Secret": "wrong"})
        t1_b = res.status_code == 403
        print(f"Invalid Secret -> {res.status_code} (Expected 403): {'PASS' if t1_b else 'FAIL'}")

        # C. Valid Secret
        with patch.object(ScanExecutionService, 'execute_scan') as mock_exec:
            res = await client.post("/scheduler/daily-scan", json=payload, headers={"X-Scheduler-Secret": "test-secret"})
            t1_c = res.status_code == 202
            print(f"Valid Secret -> {res.status_code} (Expected 202): {'PASS' if t1_c else 'FAIL'}")

    print("\n--- TEST 2 & 3: SCHEDULER FLOW & BACKGROUND EXECUTION ---")
    mock_response = ScreenerResponse(
        scanned_symbols=1,
        data_valid_symbols=["TCS"],
        eligible_symbols=["TCS"],
        matched_symbols=["TCS"],
        shortlisted_symbols=["TCS"],
        buy_candidate_symbols=["TCS"],
        watch_candidate_symbols=[],
        data_source="mock",
        stopped_at_stage="complete",
        screener_name="test_screener",
        matches=[],
        disclaimer="test disclaimer"
    )

    class LogCaptureHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(self.format(record))

    caplog = LogCaptureHandler()
    logging.getLogger("backend.app.routes.scheduler").addHandler(caplog)
    logging.getLogger("backend.app.services.scan_execution_service").addHandler(caplog)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(RouterAgent, 'screener_full', return_value=mock_response) as mock_agent:
            with patch("backend.app.services.scan_execution_service.LatestScanService.persist_successful_scan") as mock_persist:
                with patch("backend.app.services.scan_execution_service.save_latest_scan") as mock_save:
                    mock_db = MagicMock()
                    mock_db.__aenter__.return_value = mock_db
                    
                    with patch("backend.app.services.scan_execution_service.AsyncSessionLocal", return_value=mock_db):
                        res = await client.post("/scheduler/daily-scan", json=payload, headers={"X-Scheduler-Secret": "test-secret"})
                        t2_1 = res.status_code == 202
                        
                        # wait for background task to complete
                        await asyncio.sleep(0.5)
                        
                        logs = "\n".join(caplog.records)
                        
                        t2_3 = "SCAN_TRIGGER_ACCEPTED" in logs
                        t2_4 = "SCAN_STARTED" in logs
                        t3_1 = mock_agent.called
                        t4_1 = mock_persist.called
                        
                        print(f"Returns immediately (202): {'PASS' if t2_1 else 'FAIL'}")
                        print(f"Logs SCAN_TRIGGER_ACCEPTED: {'PASS' if t2_3 else 'FAIL'}")
                        print(f"Logs SCAN_STARTED: {'PASS' if t2_4 else 'FAIL'}")
                        print(f"ScanExecutionService & Orchestrator executes in background: {'PASS' if t3_1 else 'FAIL'}")
                        print(f"Persistence succeeds: {'PASS' if t4_1 else 'FAIL'}")

    print("\n--- TEST 5: FAILURE PATHS ---")
    caplog.records.clear()
    class FyersTimeoutError(Exception): pass
    with patch.object(RouterAgent, 'screener_full', side_effect=FyersTimeoutError("Timeout")) as mock_agent:
        try:
            await ScanExecutionService._run_scan_task(payload, None, "cron")
        except Exception:
            pass
        
        logs = "\n".join(caplog.records)
        t5_1 = "SCAN_FAILED" in logs and "FyersTimeoutError" in logs
        print(f"SCAN_FAILED emitted with error type: {'PASS' if t5_1 else 'FAIL'}")

if __name__ == "__main__":
    asyncio.run(run_tests())

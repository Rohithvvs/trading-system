import datetime
import os
from typing import Dict, List, Any

try:
    import psutil
except ImportError:
    psutil = None

class ShadowRunDiagnostics:
    def __init__(self):
        self.scanner_runs: List[Dict[str, Any]] = []
        self.scheduler_runs: List[Dict[str, Any]] = []
        self.fyers_metrics = {
            "request_count": 0,
            "failed_request_count": 0,
            "auth_failures": 0,
            "timeout_count": 0,
            "retry_count": 0,
            "rate_limit_count": 0
        }
        self.dashboard_snapshots: List[Dict[str, Any]] = []
        # Store latest scanner memory reading
        self.latest_scanner_memory = {
            "before_run_mb": 0.0,
            "after_run_mb": 0.0
        }
        self.last_scan_status = None
        self.last_scan_error = None
        self.last_successful_scan_time = None
        self.last_successful_scan_id = None
        self.last_failed_scan_time = None

    def set_scanner_running(self):
        self.last_scan_status = "RUNNING"

    def set_scanner_success(self, scan_id: str):
        self.last_scan_status = "SUCCESS"
        self.last_scan_error = None
        self.last_successful_scan_time = datetime.datetime.utcnow().isoformat()
        self.last_successful_scan_id = scan_id

    def set_scanner_failed(self, error_message: str):
        self.last_scan_status = "FAILED"
        self.last_scan_error = str(error_message)[:500] if error_message else "Unknown Error"
        self.last_failed_scan_time = datetime.datetime.utcnow().isoformat()

    def record_scanner_run(self, data: Dict[str, Any]):
        self.scanner_runs.append(data)
        if len(self.scanner_runs) > 50:
            self.scanner_runs.pop(0)

    def record_scheduler_run(self, data: Dict[str, Any]):
        self.scheduler_runs.append(data)
        if len(self.scheduler_runs) > 100:
            self.scheduler_runs.pop(0)
            
    def increment_fyers_metric(self, metric: str):
        if metric in self.fyers_metrics:
            self.fyers_metrics[metric] += 1

    def record_dashboard_snapshot(self, data: Dict[str, Any]):
        self.dashboard_snapshots.append(data)
        if len(self.dashboard_snapshots) > 100:
            self.dashboard_snapshots.pop(0)
            
    def set_scanner_memory(self, before: float, after: float):
        self.latest_scanner_memory["before_run_mb"] = before
        self.latest_scanner_memory["after_run_mb"] = after

    def get_memory_metrics(self) -> Dict[str, Any]:
        rss_mb = 0.0
        if psutil:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            rss_mb = round(mem_info.rss / (1024 * 1024), 2)
        return {
            "process_memory_mb": rss_mb,
            "scanner_memory_before_run_mb": round(self.latest_scanner_memory["before_run_mb"], 2),
            "scanner_memory_after_run_mb": round(self.latest_scanner_memory["after_run_mb"], 2)
        }

    async def get_db_health(self, db) -> Dict[str, Any]:
        from sqlalchemy import text
        try:
            res = await db.execute(text("SELECT state, count(*) FROM pg_stat_activity GROUP BY state"))
            states = dict(res.all())
            return {
                "active_connections": states.get("active", 0),
                "idle_connections": states.get("idle", 0),
                "idle_in_transaction": states.get("idle in transaction", 0),
                "pool_exhaustion_events": 0 # Tracked via SQLAlchemy events if needed, mocked for now
            }
        except Exception:
            return {"error": "Failed to fetch db health"}

    async def get_shadow_run_report(self, db) -> Dict[str, Any]:
        # Scanner Summary
        scanner_summary = {
            "total_runs": len(self.scanner_runs),
            "runs": self.scanner_runs
        }
        
        # Scheduler Summary
        scheduler_summary = {
            "total_runs": len(self.scheduler_runs),
            "runs": self.scheduler_runs
        }
        
        # FYERS Summary
        fyers_summary = self.fyers_metrics.copy()
        
        # Dashboard Summary
        total_dash_requests = len(self.dashboard_snapshots)
        avg_resp_time = 0
        failed_dash_requests = 0
        if total_dash_requests > 0:
            avg_resp_time = sum(d.get("response_time_ms", 0) for d in self.dashboard_snapshots) / total_dash_requests
            failed_dash_requests = sum(1 for d in self.dashboard_snapshots if d.get("record_count", 0) == 0)
            
        dashboard_summary = {
            "latest_scan_requests": total_dash_requests,
            "avg_response_time_ms": round(avg_resp_time, 2),
            "failed_requests": failed_dash_requests
        }
        
        # DB Metrics
        db_health = await self.get_db_health(db)
        from sqlalchemy import text
        try:
            res_snapshots = await db.execute(text("SELECT count(*) FROM scan_snapshots"))
            res_records = await db.execute(text("SELECT count(*) FROM scan_snapshot_records"))
            snapshot_count = res_snapshots.scalar()
            record_count = res_records.scalar()
        except Exception:
            snapshot_count = 0
            record_count = 0
            
        db_health["scan_snapshot_count"] = snapshot_count
        db_health["scan_snapshot_record_count"] = record_count
        
        database_summary = db_health
        
        # Runtime Summary
        runtime_summary = self.get_memory_metrics()
        
        return {
            "scheduler_summary": scheduler_summary,
            "scanner_summary": scanner_summary,
            "fyers_summary": fyers_summary,
            "database_summary": database_summary,
            "dashboard_summary": dashboard_summary,
            "runtime_summary": runtime_summary,
            "scanner_status": {
                "last_scan_status": self.last_scan_status,
                "last_scan_error": self.last_scan_error,
                "last_successful_scan_time": self.last_successful_scan_time,
                "last_successful_scan_id": self.last_successful_scan_id,
                "last_failed_scan_time": self.last_failed_scan_time
            }
        }

diagnostics = ShadowRunDiagnostics()

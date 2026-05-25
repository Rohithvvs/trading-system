import pytest
from unittest.mock import patch, MagicMock

# The scheduler setup is inside main.py and initializes on import or inside lifespan.
# We will mock the APScheduler instance to inspect the jobs registered.

@pytest.fixture
def mock_scheduler():
    with patch("backend.app.main.scheduler") as mock_sched:
        yield mock_sched

@pytest.mark.asyncio
async def test_market_lifecycle_cron_jobs():
    from backend.app.main import scheduler, lifespan
    from backend.app.config import settings
    from fastapi import FastAPI
    app = FastAPI()
    
    with patch.object(settings, "app_env", "prod"):
        with patch("backend.app.services.candle_store.init_db"), \
             patch("backend.app.main.scheduler.shutdown"), \
             patch("backend.app.main.market_engine.start_loop"):
            async with lifespan(app):
                jobs = scheduler.get_jobs()
                job_ids = [j.id for j in jobs]
                
                # Domain 7 Requirement: Verification of 08:55 / 09:00 / 15:30 jobs
                assert "market_engine_spin_up" in job_ids
                assert "pre_market_deep_scan" in job_ids
                assert "market_engine_cool_down" in job_ids
                assert "track_strategy_drift_job" in job_ids
                
                # Assert Timezone Awareness
                for job in jobs:
                    # All market crons MUST execute in Asia/Kolkata
                    assert str(job.trigger.timezone) == "Asia/Kolkata"

                # Heartbeats typically run on intervals (e.g. every 5 mins) between market hours
                heartbeat_jobs = [j for j in jobs if "heartbeat" in j.id.lower()]
                assert len(heartbeat_jobs) > 0

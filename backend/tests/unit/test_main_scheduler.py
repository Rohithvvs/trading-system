import pytest
from unittest.mock import patch, MagicMock
import asyncio

# Assuming main.py has lifespan that starts the scheduler
# Note: Since lifespan is an async generator, we will test the job creation logic directly 
# by importing the app and checking the apscheduler instance if it's exposed, 
# or by mocking APScheduler.

@pytest.fixture
def mock_scheduler():
    with patch("backend.app.main.scheduler") as mock_sched:
        yield mock_sched

def test_market_lifecycle_jobs_registered():
    from backend.app.main import scheduler
    
    # In a real environment, jobs are added synchronously in the module level or via lifespan.
    # We inspect the APScheduler jobs to verify the 4 jobs exist and have the correct timezone/cron.
    
    jobs = scheduler.get_jobs()
    job_ids = [j.id for j in jobs]
    
    # 1. Spin Up
    assert "market_engine_spin_up" in job_ids
    spin_up_job = next(j for j in jobs if j.id == "market_engine_spin_up")
    assert str(spin_up_job.trigger.timezone) == "Asia/Kolkata"
    
    # 2. Deep Scan
    assert "pre_market_deep_scan" in job_ids
    
    # 3. Heartbeats
    assert "intraday_heartbeat_1" in job_ids
    assert "intraday_heartbeat_2" in job_ids
    
    # 4. Cool Down
    assert "market_engine_cool_down" in job_ids
    cool_down_job = next(j for j in jobs if j.id == "market_engine_cool_down")
    assert str(cool_down_job.trigger.timezone) == "Asia/Kolkata"
    
    # 5. Strategy Drift Tracker
    assert "track_strategy_drift_job" in job_ids
    drift_job = next(j for j in jobs if j.id == "track_strategy_drift_job")
    # Verify it runs on Friday
    assert "fri" in str(drift_job.trigger)

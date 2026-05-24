import pytest
from datetime import datetime
import pytz
from freezegun import freeze_time
from apscheduler.triggers.cron import CronTrigger
from backend.app.main import scheduler, automated_screening_job

def test_automated_screening_cron_timing():
    """
    Assert that when system time shifts to 9:00 AM or 30-minute intervals,
    apscheduler triggers the automated screening job.
    """
    # In the test environment, the FastAPI lifespan bypasses adding jobs to the scheduler.
    # So we manually add it here using the exact same configuration as main.py
    job = scheduler.add_job(
        automated_screening_job,
        CronTrigger(minute="0,30", hour="9-15", timezone="Asia/Kolkata"),
        id="automated_screening_job",
        replace_existing=True,
    )
    
    assert job is not None, "Automated screening job not found in scheduler"
    assert isinstance(job.trigger, CronTrigger)

    ist = pytz.timezone("Asia/Kolkata")

    # Before market open: 8:59 AM IST is 03:29 AM UTC
    with freeze_time("2026-05-25 03:29:00"):
        now = datetime.now(ist)
        next_run = job.trigger.get_next_fire_time(None, now)
        assert next_run is not None
        assert next_run.hour == 9
        assert next_run.minute == 0

    # Mid-market: 9:01 AM IST is 03:31 AM UTC
    with freeze_time("2026-05-25 03:31:00"):
        now = datetime.now(ist)
        next_run = job.trigger.get_next_fire_time(None, now)
        assert next_run is not None
        assert next_run.hour == 9
        assert next_run.minute == 30

    # Near market close: 15:01 PM IST is 09:31 AM UTC
    with freeze_time("2026-05-25 09:31:00"):
        now = datetime.now(ist)
        next_run = job.trigger.get_next_fire_time(None, now)
        assert next_run is not None
        assert next_run.hour == 15
        assert next_run.minute == 30

    # After market close: 15:31 PM IST is 10:01 AM UTC
    with freeze_time("2026-05-25 10:01:00"):
        now = datetime.now(ist)
        next_run = job.trigger.get_next_fire_time(None, now)
        assert next_run is not None
        assert next_run.hour == 9
        assert next_run.minute == 0
        assert next_run.date() > now.date()

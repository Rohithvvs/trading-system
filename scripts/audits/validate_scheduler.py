import asyncio
import os
import sys

# Ensure backend package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from backend.app.main import app, scheduler

async def main():
    print("Application loaded successfully.")
    
    jobs = scheduler.get_jobs()
    print("Scheduler Jobs Registered:", len(jobs))
    for job in jobs:
        print(f"- {job.id}: {job.trigger}")

if __name__ == "__main__":
    asyncio.run(main())

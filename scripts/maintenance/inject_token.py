import sys
import os
import asyncio
from datetime import datetime, timezone

sys.path.append(r"F:\trading system01\trading system\backend")
from backend.app.config import settings
from backend.app.db.session import AsyncSessionLocal
from backend.app.models.fyers_token import FyersToken
from sqlalchemy import select, update

async def inject_token():
    token_str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIl0sImF0X2hhc2giOiJnQUFBQUFCcUdsQk1pMHhiUGJUTUtVSUZVM0ZkWGk4SXpGNDNnV21MV3Q4NnZubTE4RHpkRkdXY0JhUFFkNWh0QWFTU3lITkplUTFzQzhQZ1lTSHBsckgzVU9aVExNdGJDdExiaC1md1Z0WkV2Vk5JNldicFVqZz0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiJlMWYxMTgxMjVlNjgzMDRlYzhkZDI4MDcxM2UyNjk4Y2EwZmE1YmQ5OWMyNjUwN2RjZDA1OTAyMyIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiWUowODcxOCIsImFwcFR5cGUiOjEwMCwiZXhwIjoxNzgwMTg3NDAwLCJpYXQiOjE3ODAxMDkzODgsImlzcyI6ImFwaS5meWVycy5pbiIsIm5iZiI6MTc4MDEwOTM4OCwic3ViIjoiYWNjZXNzX3Rva2VuIn0.22EqteAUOZxQf8tkFjXm1WVphN8bUuz4TLx6uwjxgxg"
    async with AsyncSessionLocal() as db:
        # deactivate all
        await db.execute(update(FyersToken).values(is_active=False))
        # insert new
        new_token = FyersToken(
            access_token=token_str,
            access_token_saved_at=datetime.now(timezone.utc),
            status="active",
            is_active=True
        )
        db.add(new_token)
        await db.commit()
        print("Token injected successfully.")

if __name__ == "__main__":
    asyncio.run(inject_token())

import sys
import asyncio
import re

content = open('backend/app/services/market_engine_service.py').read()

# Fix broken indentation in line 348
content = content.replace("                def _get_acc():\n            with SessionLocal() as s:", "                def _get_acc():\n                    with SessionLocal() as s:")

# Replace PaperTradingService(db).add_notification in _pause_for_token
old_323 = """        await PaperTradingService(db).add_notification(
            account.id,
            "FYERS token expired; monitoring paused.",
            "error",
            "TOKEN_EXPIRED",
            "engine",
            session.id,
            dedupe_key=f"token-expired:{session.id}",
            commit=False,
        )"""
new_323 = """        def _add_notif(acc_id, sid):
            with SessionLocal() as s:
                PaperTradingService(s).add_notification(acc_id, "FYERS token expired; monitoring paused.", "error", "TOKEN_EXPIRED", "engine", sid, dedupe_key=f"token-expired:{sid}", commit=True)
        await asyncio.to_thread(_add_notif, account_id, session.id)"""
content = content.replace(old_323, new_323)

# Replace PaperTradingService(db).add_notification in _on_feed_error
old_351 = """                await PaperTradingService(db).add_notification(
                    account.id,
                    "Live market feed disconnected; monitoring degraded while retrying.",
                    "error",
                    "WEBSOCKET_DISCONNECTED",
                    "engine",
                    session.id,
                    dedupe_key=f"feed-disconnected:{session.id}",
                    commit=False,
                )"""
new_351 = """                def _add_err_notif(acc_id, sid):
                    with SessionLocal() as s:
                        PaperTradingService(s).add_notification(acc_id, "Live market feed disconnected; monitoring degraded while retrying.", "error", "WEBSOCKET_DISCONNECTED", "engine", sid, dedupe_key=f"feed-disconnected:{sid}", commit=True)
                await asyncio.to_thread(_add_err_notif, account_id, session.id)"""
content = content.replace(old_351, new_351)

with open('backend/app/services/market_engine_service.py', 'w') as f:
    f.write(content)

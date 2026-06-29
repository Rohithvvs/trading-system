import sys
import asyncio

content = open('backend/app/services/market_engine_service.py').read()

old_1 = """                await service.add_notification(
                    account.id,
                    f"{symbol} paper buy auto-filled at Rs {round(price, 2)}.",
                    "success",
                    "ENTRY_FILLED",
                    "order",
                    order.id,
                    dedupe_key=f"entry-filled:{order.id}",
                    commit=False,
                )"""
new_1 = """                def _add_notif(acc_id, oid):
                    with SessionLocal() as s:
                        PaperTradingService(s).add_notification(
                            acc_id, f"{symbol} paper buy auto-filled at Rs {round(price, 2)}.",
                            "success", "ENTRY_FILLED", "order", oid, dedupe_key=f"entry-filled:{oid}", commit=True)
                await asyncio.to_thread(_add_notif, account.id, order.id)"""
content = content.replace(old_1, new_1)

old_2 = """        account = await PaperTradingService(db)._get_or_create_account()"""
new_2 = """        def _get_acc():
            with SessionLocal() as s:
                return PaperTradingService(s)._get_or_create_account().id
        account_id = await asyncio.to_thread(_get_acc)"""
content = content.replace(old_2, new_2)

old_3 = """        await PaperTradingService(db).add_notification(
            account.id,
            f"Market {'OPEN' if connected else 'CLOSED'} (Feed Event)",
            "info",
            "FEED_EVENT",
        )"""
new_3 = """        def _add_notif_2(acc_id):
            with SessionLocal() as s:
                PaperTradingService(s).add_notification(acc_id, f"Market {'OPEN' if connected else 'CLOSED'} (Feed Event)", "info", "FEED_EVENT")
        await asyncio.to_thread(_add_notif_2, account_id)"""
content = content.replace(old_3, new_3)

# Fix the usage of account.id on the next lines
content = content.replace("account.id", "account_id", 1)  # Only the first one after old_2 replacement (which is actually in old_3)

old_4 = """                account = await PaperTradingService(db)._get_or_create_account()
                await PaperTradingService(db).add_notification(
                    account.id,
                    f"Feed Disconnected: {message}",
                    "error",
                    "FEED_ERROR",
                )"""
new_4 = """                def _add_err_notif():
                    with SessionLocal() as s:
                        svc = PaperTradingService(s)
                        acc = svc._get_or_create_account()
                        svc.add_notification(acc.id, f"Feed Disconnected: {message}", "error", "FEED_ERROR")
                await asyncio.to_thread(_add_err_notif)"""
content = content.replace(old_4, new_4)

with open('backend/app/services/market_engine_service.py', 'w') as f:
    f.write(content)

import os

path = r'F:\trading system01\trading system\backend\app\services\screener_service.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_fetch = "new_candles = await asyncio.to_thread(self.fyers_service.fetch_incremental_ohlcv, symbol, dummy_cache)"
new_fetch = "new_candles = await asyncio.get_running_loop().run_in_executor(self.fyers_service._network_pool, lambda: self.fyers_service.fetch_incremental_ohlcv(symbol, dummy_cache))"

old_upsert = "await asyncio.to_thread(md_service.upsert_candles, symbol, '1D', df)"
new_upsert = "await asyncio.get_running_loop().run_in_executor(self.fyers_service._network_pool, lambda: md_service.upsert_candles(symbol, '1D', df))"

content = content.replace(old_fetch, new_fetch)
content = content.replace(old_upsert, new_upsert)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("screener_service patched for deadlock")

import os

path = r'F:\trading system01\trading system\backend\app\services\fyers_service.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_init = '''    _ltp_source_cache: dict[str, str] = {}
    _ltp_locks: dict[str, "asyncio.Lock"] = {}

    def __init__(self) -> None:
        self.logger = get_logger("app.fyers")'''

new_init = '''    _ltp_source_cache: dict[str, str] = {}
    _ltp_locks: dict[str, "asyncio.Lock"] = {}
    _network_pool = __import__("concurrent.futures").futures.ThreadPoolExecutor(max_workers=20, thread_name_prefix="fyers_net")

    def __init__(self) -> None:
        self.logger = get_logger("app.fyers")'''

old_fetch_ltp = '''            # Task 3: Isolate Blocking I/O using asyncio.to_thread
            response = await asyncio.wait_for(
                asyncio.to_thread(client.quotes, data={"symbols": self._normalize_symbol(symbol)}),
                timeout=5.0
            )'''

new_fetch_ltp = '''            # Task 3: Isolate Blocking I/O using asyncio.to_thread
            response = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    FyersService._network_pool,
                    lambda: client.quotes(data={"symbols": self._normalize_symbol(symbol)})
                ),
                timeout=5.0
            )'''

content = content.replace(old_init, new_init)
content = content.replace(old_fetch_ltp, new_fetch_ltp)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("fyers_service patched for deadlock")

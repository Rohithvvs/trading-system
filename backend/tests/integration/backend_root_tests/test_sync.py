import asyncio
import concurrent.futures

_SYNC_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=5)

def _run_sync(coro):
    return _SYNC_EXECUTOR.submit(asyncio.run, coro).result()

async def load_candles():
    return [1, 2, 3]

def main():
    res = _run_sync(load_candles())
    print("Result:", res, type(res))

if __name__ == '__main__':
    main()

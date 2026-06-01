import os

path = r'F:\trading system01\trading system\backend\app\services\fyers_service.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

with open(path, 'w', encoding='utf-8') as f:
    for i, line in enumerate(lines):
        if 273 <= i <= 350:
            f.write('    ' + line)
        else:
            f.write(line)

path_pt = r'F:\trading system01\trading system\backend\app\services\paper_trading_service.py'
with open(path_pt, 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''        if include_ta:
            # We need daily candles for TA
            # fetch_ohlcv is async, we need to bridge it
            try:
                future2 = asyncio.run_coroutine_threadsafe(
                    self.fyers_service.fetch_ohlcv(symbol, mode="swing", resolution="1d", lookback=90),
                    main_event_loop
                )
                candles = future2.result(timeout=5)
            except Exception as e:
                self.logger.error(f'Error fetching TA candles: {e}')
                candles = []'''

new_code = '''        if include_ta:
            # We need daily candles for TA
            try:
                from ..schemas import AnalysisMode
                candles = self.fyers_service.fetch_ohlcv(symbol, mode=AnalysisMode.swing, resolution="1d", lookback=90)
            except Exception as e:
                self.logger.error(f'Error fetching TA candles: {e}')
                candles = []'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(path_pt, 'w', encoding='utf-8') as f:
        f.write(content)
    print("paper_trading_service patched successfully")
else:
    print("old_code not found in paper_trading_service")

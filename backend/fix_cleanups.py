import glob
import os

files = glob.glob('app/tests_pg/*.py')
for f in files:
    with open(f, 'r') as fp:
        data = fp.read()
    
    data = data.replace('await db.execute(text("DELETE FROM paper_trading_accounts"))', 'await db.execute(text("TRUNCATE paper_trading_trade_history, paper_trading_transactions, paper_trading_positions, paper_trading_orders, paper_trading_accounts, migration_checkpoints CASCADE"))')
    data = data.replace('await db.execute(text("DELETE FROM paper_trading_orders"))\n', '')
    data = data.replace('await db.execute(text("DELETE FROM migration_checkpoints"))\n', '')
    
    with open(f, 'w') as fp:
        fp.write(data)

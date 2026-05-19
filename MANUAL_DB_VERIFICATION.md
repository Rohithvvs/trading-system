# Paper Trading Database Verification Guide

Use the following SQL queries to manually verify the new read architecture is correctly persisting data and separating concerns.

## Database Location
```
F:\trading system01\trading system\backend\app\db\trading_system.db
```

## 1. Verify Open Positions (DB Truth vs UI Truth)

### Schema Check
```sql
.schema paper_position
```

### Count of Open Positions
```sql
SELECT COUNT(*) as open_positions_count
FROM paper_position
WHERE status = 'OPEN';
```

### All Open Positions Details
```sql
SELECT 
  id,
  symbol,
  qty,
  avg_entry_price,
  current_price,
  stop_loss,
  target,
  lifecycle_state,
  created_at,
  updated_at
FROM paper_position
WHERE status = 'OPEN'
ORDER BY created_at DESC;
```

**Expected Behavior:**
- One row per open position
- `status = 'OPEN'`
- `lifecycle_state IN ('OPEN_POSITION', 'PAUSED_ENTRY', 'PAUSED_EXIT')`
- `qty > 0`
- `current_price` should match last quote fetch time

## 2. Verify Pending Orders (Open Orders Tab Data)

### Count of Pending Orders
```sql
SELECT COUNT(*) as pending_orders_count
FROM paper_order
WHERE status = 'PENDING'
  AND account_id = (SELECT id FROM paper_trading_account LIMIT 1);
```

### All Pending Orders
```sql
SELECT 
  id,
  symbol,
  side,
  order_type,
  qty,
  order_price,
  stop_price,
  stop_loss,
  target,
  status,
  lifecycle_state,
  notes,
  created_at
FROM paper_order
WHERE status = 'PENDING'
  AND account_id = (SELECT id FROM paper_trading_account LIMIT 1)
ORDER BY created_at DESC;
```

**Expected Behavior:**
- Rows have `status = 'PENDING'`
- `lifecycle_state IN ('PENDING_ENTRY', 'TOKEN_EXPIRED_PAUSED', 'MARKET_CLOSED_WAITING')`
- NOT included in position counts
- Each pending BUY reduces available cash (reserved)

## 3. Verify Trade History (Completed Trades)

### Count of Closed Trades
```sql
SELECT COUNT(*) as completed_trades_count
FROM paper_trade_history
WHERE account_id = (SELECT id FROM paper_trading_account LIMIT 1);
```

### All Closed Trades with PnL
```sql
SELECT 
  id,
  symbol,
  qty,
  entry_price,
  exit_price,
  pnl,
  pnl_percent,
  exit_reason,
  opened_at,
  closed_at,
  notes
FROM paper_trade_history
WHERE account_id = (SELECT id FROM paper_trading_account LIMIT 1)
ORDER BY closed_at DESC;
```

**Expected Behavior:**
- One row per completed round-trip trade (buy + sell)
- `pnl = (exit_price - entry_price) * qty`
- `pnl_percent = (pnl / (entry_price * qty)) * 100`
- `exit_reason IN ('MANUAL', 'STOPLOSS_HIT', 'TARGET_HIT', 'AUTO_EXIT')`
- Holds the original entry/exit prices for auditing

## 4. Verify Lifecycle State Separation

### Lifecycle States in Orders
```sql
SELECT DISTINCT lifecycle_state, COUNT(*) as count
FROM paper_order
WHERE account_id = (SELECT id FROM paper_trading_account LIMIT 1)
GROUP BY lifecycle_state
ORDER BY count DESC;
```

### Lifecycle States in Positions
```sql
SELECT DISTINCT lifecycle_state, COUNT(*) as count
FROM paper_position
WHERE account_id = (SELECT id FROM paper_trading_account LIMIT 1)
GROUP BY lifecycle_state
ORDER BY count DESC;
```

**Expected States:**
- **Order lifecycle**: PENDING_ENTRY, ENTRY_FILLED, EXIT_FILLED, CANCELLED, TOKEN_EXPIRED_PAUSED, MARKET_CLOSED_WAITING, ERROR_RETRYING
- **Position lifecycle**: OPEN_POSITION, PAUSED_ENTRY, PAUSED_EXIT

## 5. Account Summary Verification

### Account Cash & Equity Calculation
```sql
SELECT 
  id,
  name,
  starting_balance,
  cash_balance,
  MAX(updated_at) as last_update
FROM paper_trading_account
LIMIT 1;
```

### Invested Capital (should match positions)
```sql
SELECT 
  SUM(avg_entry_price * qty) as total_invested_in_positions
FROM paper_position
WHERE status = 'OPEN'
  AND account_id = (SELECT id FROM paper_trading_account LIMIT 1);
```

### Reserved Cash (pending orders)
```sql
SELECT 
  SUM(CASE WHEN side = 'BUY' THEN order_price * qty ELSE 0 END) as cash_reserved_for_buy_orders
FROM paper_order
WHERE status = 'PENDING'
  AND side = 'BUY'
  AND account_id = (SELECT id FROM paper_trading_account LIMIT 1);
```

**Expected Behavior:**
- `cash_balance + total_invested_in_positions + cash_reserved_for_buy_orders ≈ starting_balance` (within rounding)
- All cash is accounted for
- No orphaned orders or positions

## 6. Verify Price Metadata Columns (New Schema)

### Check paper_position for price metadata
```sql
PRAGMA table_info(paper_position);
```

**Should include:**
- `current_price FLOAT` (last fetched LTP)
- `last_fetched_at DATETIME` (when price was last updated)
- May not have price_source in this table; it's computed at response time

### Check paper_order for price metadata
```sql
PRAGMA table_info(paper_order);
```

**Should include:**
- `last_seen_ltp FLOAT`
- `last_evaluated_at DATETIME`

## 7. Order Fill Sequence Verification

### Find a completed BUY order and its position
```sql
SELECT o.id as order_id, o.symbol, o.side, o.qty, o.filled_price, o.filled_at, o.status,
       p.id as position_id, p.avg_entry_price, p.status as position_status
FROM paper_order o
LEFT JOIN paper_position p ON o.symbol = p.symbol AND p.status = 'OPEN'
WHERE o.status = 'FILLED' AND o.side = 'BUY'
  AND o.account_id = (SELECT id FROM paper_trading_account LIMIT 1)
LIMIT 1;
```

**Expected Behavior:**
- If BUY order is FILLED, there should be a matching OPEN position
- `position.avg_entry_price ≈ order.filled_price`
- Position was created after order was filled

### Verify transaction log
```sql
SELECT 
  id,
  symbol,
  action,
  qty,
  price,
  amount,
  balance_after,
  timestamp
FROM paper_transaction
WHERE account_id = (SELECT id FROM paper_trading_account LIMIT 1)
ORDER BY timestamp DESC
LIMIT 10;
```

**Expected:** One BUY transaction per filled buy order, one SELL transaction per filled sell order

## 8. Data Persistence After Backend Reload

Run these queries immediately before and after restarting the backend server.

### Before restart: Note the state
```sql
SELECT 
  (SELECT COUNT(*) FROM paper_position WHERE status = 'OPEN' 
     AND account_id = (SELECT id FROM paper_trading_account)) as open_positions,
  (SELECT COUNT(*) FROM paper_order WHERE status = 'PENDING'
     AND account_id = (SELECT id FROM paper_trading_account)) as pending_orders,
  (SELECT COUNT(*) FROM paper_trade_history
     AND account_id = (SELECT id FROM paper_trading_account)) as completed_trades,
  (SELECT cash_balance FROM paper_trading_account LIMIT 1) as cash_balance;
```

### After restart: Verify unchanged
```sql
-- Run the same query above
```

**Expected:** Identical counts and balances (data survived restart)

## Command-Line Usage

Open SQLite directly:
```powershell
cd "F:\trading system01\trading system"
sqlite3 backend/app/db/trading_system.db
```

Then paste any of the SQL queries above.

## API vs Database Verification

### Check what the dedic API endpoints return
```powershell
# Terminal 1: Start backend
cd backend
uvicorn main:app --reload --port 8000

# Terminal 2: Query endpoints
curl -X GET "http://localhost:8000/paper-trading/positions"
curl -X GET "http://localhost:8000/paper-trading/orders/pending"
curl -X GET "http://localhost:8000/paper-trading/orders/history"
curl -X GET "http://localhost:8000/paper-trading/trades"
curl -X GET "http://localhost:8000/paper-trading/dashboard"
```

**Compare API response data against database queries above.**

- Positions should match `/positions` endpoint
- Pending orders should match `/orders/pending`
- Order history should match `/orders/history`
- Trades should match `/trades`
- Dashboard should aggregate all of the above correctly

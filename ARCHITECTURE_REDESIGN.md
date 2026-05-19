# Paper Trading Read Architecture Redesign
## Architecture-First Design (No Code Changes Yet)

**Date:** May 18, 2026  
**Scope:** Backend read queries, API contracts, frontend state architecture  
**Goal:** Clear source of truth for all Paper Trading screen data

---

## 1. CURRENT ARCHITECTURE PROBLEMS

### Problem 1.1: Data Categorization Confusion
**Current State:**
- Single `GET /paper-trading/dashboard` endpoint returns one large payload
- Payload mixes **active** (PENDING orders, OPEN positions) with **historical** (FILLED orders, closed trades)
- Backend `_order_models()` returns ALL orders; Python filters in response builder
- Frontend receives 100+ old FILLED orders; serialization bloats response

**Symptom:**
- User opens Paper Trading screen → sees positions from days ago mixed with today's positions
- After market close, unclear which positions are being monitored vs paused
- Response times vary wildly (5 seconds today, 500ms after reset)

### Problem 1.2: State Visibility Gap
**Current State:**
- Backend sets `lifecycle_state = "MARKET_CLOSED_WAITING"` when market closes
- API response doesn't expose `lifecycle_state`, only `status`
- Frontend can't show "Paused", "Waiting for Market", "Token Expired", etc.

**Symptom:**
- User sees order listed after market close but doesn't know if it's still active
- User thinks position is being monitored when it's actually paused
- No indication that action is required (token refresh, etc.)

### Problem 1.3: Price Metadata Missing
**Current State:**
- `current_price` is fetched once per dashboard load
- No timestamp indicating when price was fetched
- No indication if price is FYERS live vs candle fallback vs stale

**Symptom:**
- Position shows ₹1,500 but market moved to ₹1,550; user doesn't know price is stale
- Unrealized P&L appears wrong but user doesn't know it's due to stale price
- No way to debug "why is the dashboard different than real market?"

### Problem 1.4: Tab Navigation Architecture Ambiguity
**Current State:**
- All tabs (Positions, Open Orders, History, Account) load from **one** endpoint
- Switching tabs doesn't make new API call; uses cached response
- Stale data persists across tab switches

**Symptom:**
- User opens History tab 2 hours ago, switches to Positions, then back to History
- History still shows data from 2 hours ago, not refreshed
- User must reload entire page to see fresh history

### Problem 1.5: Active vs Historical Data Mixing
**Current State:**
- `_order_models()` returns PENDING, FILLED, CANCELLED without filtering
- `_trade_models()` returns all trades (even month-old ones)
- No distinction between "today's history" and "all-time history"

**Symptom:**
- Positions tab shows 5 rows (hard to scan)
- Open Orders tab shows 15 rows (mostly old FILLED orders from backend, filtered in frontend)
- History tab shows 100+ rows (scrolling takes forever)

---

## 2. PROPOSED TARGET ARCHITECTURE

### 2.1 Principle: Separation of Concerns by Tab

**Design Decision:**
- Each Paper Trading tab (Positions, Open Orders, History, Account) gets its own **query function** and optional **dedicated route**
- Positions and Open Orders share a "live/active" query family
- History shares an "archived/historical" query family
- Account has its own summary calculation
- Routes can be shared or split based on polling frequency

**Rationale:**
- Active data (OPEN positions, PENDING orders) changes every second → can be cached 0-5 seconds
- Historical data (trade history, closed orders) changes rarely → can be cached 30-60 seconds
- Account summary is calculated from both → cached 5-10 seconds
- Each route can have appropriate TTL

### 2.2 Principle: Lifecycle State Visibility

**Design Decision:**
- All active entities (positions, orders) expose:
  - `lifecycle_state`: explicit state ("OPEN_POSITION", "MARKET_CLOSED_WAITING", etc.)
  - `paused_reason`: human-readable reason if paused ("MARKET_CLOSED", "TOKEN_EXPIRED", etc.)
  - `monitor_enabled`: boolean (user can manually pause)
  - `is_monitored_now`: calculated at response time (true if lifecycle_state is "active")

**Rationale:**
- UI can show visual indicators (🔴 Paused, ⏸️ Waiting, 🔄 Retrying, ✅ Active)
- User knows immediately why action isn't happening
- State changes visible without requiring page reload

### 2.3 Principle: Price Metadata Transparency

**Design Decision:**
- All prices include metadata:
  - `price_value`: the actual price number
  - `price_source`: enum ("FYERS_LIVE", "CANDLE_FALLBACK", "NO_DATA")
  - `price_fetched_at`: ISO timestamp
  - `price_age_seconds`: calculated (now - fetched_at)
  - `is_stale`: calculated (age_seconds > 300) // 5 min threshold

**Rationale:**
- Frontend can gray out stale prices visually
- Backend can prefetch prices and cache them
- Debugging becomes obvious: "oh, price is 3 hours old"

### 2.4 Principle: Source of Truth per Data Category

**Design Decision:**

| Data Category | Source Table | Query Filter | Lifecycle | Visibility |
|---------------|--------------|--------------|-----------|------------|
| Open Positions | `paper_trading_positions` | `status="OPEN"` | OPEN_POSITION, MARKET_CLOSED_WAITING, etc. | Positions tab + Account summary |
| Pending Orders | `paper_trading_orders` | `status="PENDING"` | PENDING_ENTRY, MARKET_CLOSED_WAITING, etc. | Open Orders tab + Account summary |
| Order History | `paper_trading_orders` | `status IN ("FILLED","CANCELLED")` | ENTRY_FILLED, EXIT_FILLED, CANCELLED | History tab (limited to last 100) |
| Trade History | `paper_trading_trade_history` | all rows | N/A (always closed) | History tab + Account P&L summary |
| Cash Balance | `paper_trading_accounts` | the one account | N/A (static) | Account tab |
| Realized P&L | calculated from `paper_trading_trade_history` | all rows | N/A | Account P&L summary |
| Unrealized P&L | calculated from `paper_trading_positions` + live prices | `status="OPEN"` | N/A | Account P&L summary |

**Rationale:**
- No ambiguity about which table to query for which purpose
- Query filters are explicit in the contract
- Historical data never pollutes active data

---

## 3. ROUTE & QUERY SEPARATION ARCHITECTURE

### 3.1 Recommended Endpoint Structure

```
GET /paper-trading/positions
├─ Returns: List of OPEN positions with lifecycle, price metadata, unrealized P&L
├─ Query: _get_open_positions(account_id)
├─ Cache: 5 seconds (live data changes frequently)
├─ Response fields: symbol, qty, entry_price, current_price, p&l, lifecycle, paused_reason, price_metadata

GET /paper-trading/orders/pending
├─ Returns: List of PENDING orders with lifecycle, price metadata
├─ Query: _get_pending_orders(account_id)
├─ Cache: 5 seconds
├─ Response fields: symbol, side, qty, order_price, status, lifecycle, paused_reason

GET /paper-trading/orders/history
├─ Returns: Last 100 FILLED + CANCELLED orders with fill_price, filled_at
├─ Query: _get_order_history(account_id, limit=100)
├─ Cache: 30 seconds
├─ Response fields: symbol, side, qty, filled_price, filled_at, status

GET /paper-trading/trades
├─ Returns: Last 50 closed trades with entry, exit, P&L, dates
├─ Query: _get_trade_history(account_id, limit=50)
├─ Cache: 30 seconds
├─ Response fields: symbol, qty, entry_price, exit_price, pnl, pnl_percent, opened_at, closed_at, exit_reason

GET /paper-trading/account
├─ Returns: Account summary: cash, invested, total capital, realized/unrealized P&L, daily P&L
├─ Query: _get_account_summary(account_id)
├─ Cache: 10 seconds
├─ Response fields: cash_balance, starting_balance, invested_value, total_capital, realized_pnl, unrealized_pnl, daily_pnl, market_status

GET /paper-trading/dashboard (DEPRECATED - kept for backward compatibility)
├─ Returns: Composite of positions + pending_orders + trades + account in one response
├─ Calls: positions + orders/pending + trades + account endpoints internally
├─ Cache: 5 seconds (limited by fastest sub-endpoint)
├─ Use: Only if frontend loads multiple tabs simultaneously
```

### 3.2 Query Functions (Backend Design)

**Active Data Query Family:**

```python
def _get_open_positions(account_id: int) -> list[PaperPosition]:
    """
    Query: SELECT * FROM paper_trading_positions 
           WHERE account_id=? AND status="OPEN"
           ORDER BY created_at DESC
    
    Filter:
    - Only OPEN positions (status="OPEN")
    - Exclude closed/archived positions (they're in trade_history)
    
    Returns: Max 100 rows (reasonable upper bound for active positions)
    """

def _get_pending_orders(account_id: int) -> list[PaperOrder]:
    """
    Query: SELECT * FROM paper_trading_orders 
           WHERE account_id=? AND status="PENDING"
           ORDER BY created_at DESC
    
    Filter:
    - Only PENDING orders (status="PENDING")
    - Exclude filled, cancelled (they're in order_history)
    - Do NOT load 200+ old FILLED orders
    
    Returns: Max 50 rows
    """

def _get_order_history(account_id: int, limit: int = 100) -> list[PaperOrder]:
    """
    Query: SELECT * FROM paper_trading_orders 
           WHERE account_id=? AND status IN ("FILLED", "CANCELLED")
           ORDER BY filled_at DESC
           LIMIT ?
    
    Filter:
    - Only FILLED or CANCELLED orders
    - Order by most recent first
    - Limit to prevent loading thousands of rows
    
    Returns: Max `limit` rows (default 100)
    """

def _get_trade_history(account_id: int, limit: int = 50) -> list[PaperTradeHistory]:
    """
    Query: SELECT * FROM paper_trading_trade_history 
           WHERE account_id=?
           ORDER BY closed_at DESC
           LIMIT ?
    
    Filter:
    - All rows (always represent closed trades)
    - Order by most recent first
    - Limit to prevent loading thousands of rows
    
    Returns: Max `limit` rows (default 50)
    """

def _get_account_summary(account_id: int) -> AccountSummaryData:
    """
    Queries:
    1. SELECT cash_balance FROM paper_trading_accounts WHERE id=?
    2. SELECT SUM(pnl) FROM paper_trading_trade_history WHERE account_id=?
    3. SELECT SUM(unrealized) FROM (
         SELECT (current_price - avg_entry_price) * qty as unrealized
         FROM paper_trading_positions WHERE account_id=? AND status="OPEN"
       )
    
    Calculations:
    - realized_pnl = sum of all trade history P&L
    - unrealized_pnl = sum of (current_price - entry_price) * qty for open positions
    - total_pnl = realized + unrealized
    - daily_pnl = sum of trade history P&L for trades closed TODAY (IST timezone)
    - available_cash = cash_balance - sum of open position investments
    - total_capital = starting_balance + realized_pnl
    
    Returns: One summary object
    """
```

**Historical Data Query Family:**

- Same as active data functions above, but with different WHERE clauses
- No mixing of PENDING + FILLED orders in response

---

## 4. RESPONSE SCHEMA DESIGN

### 4.1 Position Response

**Current:**
```json
{
  "id": 101,
  "symbol": "INFY-EQ",
  "qty": 10,
  "avg_entry_price": 1500.50,
  "current_price": 1520.00,
  "stop_loss": 1450,
  "target": 1600,
  "unrealized_pnl": 195.00,
  "unrealized_pnl_percent": 1.30,
  "created_at": "2026-05-18T10:30:00Z"
}
```

**Proposed:**
```json
{
  "id": 101,
  "symbol": "INFY-EQ",
  "qty": 10,
  "avg_entry_price": 1500.50,
  
  // ✅ Price metadata
  "current_price": 1520.00,
  "price_source": "FYERS_LIVE",  // enum: FYERS_LIVE, CANDLE_FALLBACK, NO_DATA
  "price_fetched_at": "2026-05-18T14:45:30Z",
  "price_age_seconds": 45,  // calculated at response time
  "is_price_stale": false,  // true if age > 300 seconds
  
  // ✅ Lifecycle & monitoring state
  "lifecycle_state": "OPEN_POSITION",  // enum
  "paused_reason": null,  // "MARKET_CLOSED", "TOKEN_EXPIRED", "ERROR", null if active
  "monitor_enabled": true,  // user can pause
  "is_actively_monitored": true,  // calculated: true if lifecycle in active states AND monitor_enabled
  
  "stop_loss": 1450,
  "target": 1600,
  "unrealized_pnl": 195.00,
  "unrealized_pnl_percent": 1.30,
  "created_at": "2026-05-18T10:30:00Z",
  "updated_at": "2026-05-18T14:45:30Z"
}
```

**Fields Explanation:**
- `price_*` fields: UI shows price freshness warning if stale
- `lifecycle_state`: Determines UI visual state (active, paused, waiting, error)
- `paused_reason`: Explains WHY it's paused (shown in tooltip)
- `monitor_enabled`: Separate from lifecycle_state (user manual pause)
- `is_actively_monitored`: Calculated at response time (true if both conditions met)

### 4.2 Pending Order Response

```json
{
  "id": 501,
  "symbol": "TCS-EQ",
  "side": "BUY",
  "qty": 5,
  "order_type": "LIMIT",
  "order_price": 3200.00,
  
  // ✅ Price metadata
  "current_market_price": 3250.00,
  "price_source": "FYERS_LIVE",
  "price_fetched_at": "2026-05-18T14:45:30Z",
  "price_age_seconds": 45,
  "is_price_stale": false,
  
  // ✅ Lifecycle & monitoring state
  "lifecycle_state": "PENDING_ENTRY",
  "paused_reason": null,
  "monitor_enabled": true,
  "is_actively_monitored": true,
  
  "stop_loss": 3150,
  "target": 3400,
  "status": "PENDING",
  "created_at": "2026-05-18T10:30:00Z",
  "last_evaluated_at": "2026-05-18T14:45:30Z"
}
```

### 4.3 Order History Response (Filled/Cancelled)

```json
{
  "id": 502,
  "symbol": "INFY-EQ",
  "side": "SELL",
  "qty": 10,
  "order_type": "MARKET",
  "order_price": 1520.00,
  
  "status": "FILLED",  // or "CANCELLED"
  "filled_price": 1520.50,
  "filled_at": "2026-05-18T14:45:30Z",
  
  "lifecycle_state": "EXIT_FILLED",  // indicates this was a sell order
  "created_at": "2026-05-18T10:30:00Z"
}
```

### 4.4 Trade History Response

```json
{
  "id": 1001,
  "symbol": "INFY-EQ",
  "qty": 10,
  "entry_price": 1500.50,
  "exit_price": 1520.50,
  
  "pnl": 200.00,
  "pnl_percent": 1.33,
  
  "opened_at": "2026-05-17T10:30:00Z",
  "closed_at": "2026-05-18T14:45:30Z",
  "exit_reason": "TARGET_HIT",  // or "STOPLOSS_HIT", "MANUAL", "AUTO_EXIT"
  
  "duration_minutes": 1455  // calculated
}
```

### 4.5 Account Summary Response

```json
{
  "cash_balance": 950000.00,
  "starting_balance": 1000000.00,
  
  // Invested & Available
  "invested_in_positions": 50000.00,  // sum of position.avg_entry_price * qty
  "available_cash": 950000.00,  // cash not tied up in positions
  
  // P&L
  "realized_pnl": -15000.00,  // sum of closed trade P&L
  "unrealized_pnl": 195.00,   // sum of open position P&L
  "total_pnl": -14805.00,     // realized + unrealized
  "daily_pnl": 500.00,        // sum of today's closed trades P&L (IST timezone)
  
  // Totals
  "total_capital": 985000.00,  // starting + realized_pnl
  "portfolio_value": 1000195.00,  // cash + invested + unrealized
  
  // Market status
  "market_status": "OPEN",  // "OPEN" or "CLOSED"
  "is_market_hours": true,
  
  // Monitoring status
  "active_positions": 2,
  "pending_orders": 3,
  "paused_positions": 0,
  "paused_orders": 1
}
```

### 4.6 Composite Dashboard Response (If Kept for Backward Compatibility)

```json
{
  "account": { AccountSummaryResponse },
  "positions": [ PaperPositionResponse[] ],
  "pending_orders": [ PendingOrderResponse[] ],
  "order_history": [ OrderHistoryResponse[] ],
  "trade_history": [ TradeHistoryResponse[] ],
  "notifications": [ NotificationResponse[] ],
  "last_refreshed_at": "2026-05-18T14:45:30Z",
  "cache_age_seconds": 2
}
```

---

## 5. LIFECYCLE STATE VISIBILITY MODEL

### 5.1 Lifecycle State Flow Diagram

```
                          MARKET HOURS
                               │
                        ┌──────┴──────┐
                        │             │
                   PENDING        OPEN
                   (Order)     (Position)
                        │             │
        ┌───────────────┼─────────────┼────────────┐
        │               │             │            │
   PENDING_ENTRY   MARKET    OPEN_POSITION   MARKET
                   CLOSED                    CLOSED
                   WAITING                   WAITING
        │               │             │            │
        └───────────────┼─────────────┼────────────┘
                        │             │
                   (if token expires during market hours)
                        │             │
                   TOKEN_EXPIRED_PAUSED (both)
        
        ↓ (User manually cancels / Position closed)
        CANCELLED / EXIT_FILLED
```

### 5.2 State Interpretation by UI

| Lifecycle State | Position Tab | Open Orders Tab | Meaning | Icon | Action Needed |
|-----------------|--------------|-----------------|---------|------|---------------|
| PENDING_ENTRY | N/A | ✅ Show | Order waiting for trigger | ⏱️ | None (automatic) |
| ENTRY_FILLED | ✅ Show | ✅ Show (if showing filled) | Order filled, position opened | ✅ | None |
| OPEN_POSITION | ✅ Show | N/A | Position active, monitoring | 📈 | None (automatic) |
| EXIT_FILLED | N/A (deleted from positions) | ✅ Show (in history) | Position closed (sell executed) | ✅ | None |
| MARKET_CLOSED_WAITING | ✅ Show + GRAY | ✅ Show + GRAY | Market closed, monitoring paused | ⏸️ | Wait for market open |
| TOKEN_EXPIRED_PAUSED | ✅ Show + RED | ✅ Show + RED | FYERS token expired, monitoring paused | 🔴 | User must refresh token |
| ERROR_RETRYING | ✅ Show + YELLOW | ✅ Show + YELLOW | System error, will retry | ⚠️ | Monitor logs; may auto-recover |
| CANCELLED | N/A | ✅ Show (in history) | Order manually cancelled | ❌ | None |

### 5.3 UI Rendering Logic

```javascript
// Pseudocode for position rendering in Positions tab
function renderPosition(position) {
  // Determine display state
  let displayState = 'ACTIVE';
  let grayOut = false;
  let showWarning = false;
  let warningText = '';
  
  if (position.paused_reason) {
    grayOut = true;
    switch (position.paused_reason) {
      case 'MARKET_CLOSED':
        displayState = 'PAUSED_MARKET_CLOSED';
        warningText = 'Market closed. Will resume at 9:15 AM tomorrow.';
        break;
      case 'TOKEN_EXPIRED':
        displayState = 'ERROR_TOKEN_EXPIRED';
        showWarning = true;
        warningText = 'FYERS token expired. Refresh token to resume monitoring.';
        break;
      case 'ERROR':
        displayState = 'ERROR_RETRYING';
        warningText = 'System error. Retrying automatically.';
        break;
    }
  }
  
  // If price is stale
  if (position.is_price_stale) {
    showWarning = true;
    warningText += ` | Price is ${position.price_age_seconds}s old.`;
  }
  
  // Render
  return (
    <PositionRow
      symbol={position.symbol}
      qty={position.qty}
      pnl={position.unrealized_pnl}
      grayOut={grayOut}
      icon={getIcon(displayState)}
      warning={showWarning ? warningText : null}
    />
  );
}
```

---

## 6. PRICE METADATA MODEL

### 6.1 Price Representation in API Response

**Every `current_price` field includes metadata:**

```json
{
  "current_price": 1520.00,
  "price_source": "FYERS_LIVE",        // enum: FYERS_LIVE | CANDLE_FALLBACK | NO_DATA
  "price_fetched_at": "2026-05-18T14:45:30Z",  // ISO 8601 timestamp
  "price_age_seconds": 45,             // calculated at response time
  "is_price_stale": false              // true if age_seconds > 300
}
```

### 6.2 Price Source Semantics

| Source | Meaning | Reliability | Freshness | When Used |
|--------|---------|-------------|-----------|-----------|
| FYERS_LIVE | Fetched from FYERS API | ✅ High | < 1 second | Market hours, FYERS working |
| CANDLE_FALLBACK | Last daily candle close | ⚠️ Medium | 1 hour to 1 day | FYERS down or after hours |
| NO_DATA | No price available | 🔴 Low | N/A | Market data unavailable |

### 6.3 Staleness Thresholds

| Scenario | Threshold | Action |
|----------|-----------|--------|
| Live quote during market hours | 5 seconds | Show as-is; gray if > 5s |
| Position P&L | 30 seconds | Show as-is; show warning if > 30s |
| Historical candle price | 1 hour | Show as-is; show warning if > 1h |
| Position after market close | 1 hour | Gray out price; show "as of 3:30 PM" |

### 6.4 Frontend Price Display Logic

```javascript
function priceDisplay(price, source, age) {
  let display = `₹${price.toFixed(2)}`;
  
  if (source === 'FYERS_LIVE' && age < 5) {
    return <span className="price-live">{display} 🟢</span>;  // Green dot
  }
  
  if (source === 'FYERS_LIVE' && age >= 5 && age < 30) {
    return <span className="price-stale">{display} 🟡</span>;  // Yellow dot + tooltip
  }
  
  if (source === 'CANDLE_FALLBACK') {
    return <span className="price-fallback">{display} 📊</span>;  // Chart icon + tooltip
  }
  
  if (source === 'NO_DATA') {
    return <span className="price-none">-- ⚠️</span>;  // Warning icon
  }
}
```

---

## 7. SOURCE OF TRUTH ARCHITECTURE

### 7.1 Truth Matrix

| Question | Source Table | Source Query | Backend Function | Cache Duration |
|----------|--------------|--------------|------------------|-----------------|
| **Is position INFY still open?** | paper_trading_positions | SELECT status FROM ... WHERE symbol='INFY' AND status='OPEN' | _get_open_positions() | 5 sec |
| **Is the BUY order for TCS still pending?** | paper_trading_orders | SELECT status FROM ... WHERE symbol='TCS' AND side='BUY' AND status='PENDING' | _get_pending_orders() | 5 sec |
| **Did I close INFY position?** | paper_trading_trade_history | SELECT * WHERE symbol='INFY' AND closed_at >= TODAY | _get_trade_history() | 30 sec |
| **What was INFY exit price?** | paper_trading_orders or paper_trading_trade_history | SELECT filled_price FROM orders WHERE symbol='INFY' AND status='FILLED' | _get_order_history() | 30 sec |
| **What's my realized P&L?** | paper_trading_trade_history | SELECT SUM(pnl) FROM ... WHERE account_id=? | _get_account_summary() | 10 sec |
| **What's my cash balance?** | paper_trading_accounts | SELECT cash_balance FROM ... WHERE id=? | _get_account_summary() | 10 sec |
| **What's my total portfolio value?** | derived from (positions + account + trades) | Multiple queries | _get_account_summary() | 10 sec |
| **Is INFY position being monitored?** | paper_trading_positions | SELECT lifecycle_state, monitor_enabled FROM ... WHERE symbol='INFY' | _get_open_positions() | 5 sec |

### 7.2 Never Mix These in Same Response

| Do NOT Mix | Why | Solution |
|-----------|------|----------|
| PENDING orders + FILLED orders | Different states; confuse UI | Separate `GET /orders/pending` and `GET /orders/history` |
| Today's history + month-old history | User only cares about recent | Limit history queries to last 100 rows + add date filter |
| OPEN positions + MARKET_CLOSED_WAITING positions | Second set is paused; shouldn't trigger auto-exit | Same; UI knows both are OPEN but can visually gray out paused |
| FYERS_LIVE price + CANDLE_FALLBACK price in same response for same symbol | Confuses which is real | Always fetch fresh from FYERS first; only use fallback if FYERS fails |

### 7.3 Consistency Rules

**Rule 1: Position Consistency**
- If position appears in `_get_open_positions()`, it MUST have `status="OPEN"`
- If position not in that query, it MUST have been deleted or moved to trade_history
- UI Positions tab always matches that query result

**Rule 2: Order Consistency**
- If order appears in `_get_pending_orders()`, it MUST have `status="PENDING"`
- If order not in that query, check `_get_order_history()` for FILLED/CANCELLED status
- UI Open Orders tab only shows result of first query

**Rule 3: History Consistency**
- Every closed trade MUST have corresponding row in `paper_trading_trade_history`
- Every closed position MUST be deleted from positions table (not just marked CLOSED)
- UI History tab shows this query result

**Rule 4: Price Consistency**
- Price in response must include metadata (source, fetched_at, age_seconds)
- If age > threshold, UI must show warning or gray out
- Backend must recalculate age_seconds at response time (not cache it)

---

## 8. SQL VERIFICATION STRATEGY

### 8.1 Minimum Verification Query Set

**V1: Today's Positions**
```sql
-- Verify today's bought positions still exist in OPEN state
SELECT 
  p.id, p.symbol, p.qty, p.avg_entry_price, p.status, p.lifecycle_state,
  p.created_at, p.updated_at
FROM paper_trading_positions p
WHERE p.account_id = 1 
  AND p.status = 'OPEN'
  AND p.created_at >= datetime('now', '-1 day')  -- Today's trades
ORDER BY p.created_at DESC;
```

**Expected:** Shows all positions entered today  
**Bug Symptom:** Empty result when it shouldn't be  
**Debugging:** If empty, check paper_trading_trade_history for closed entries

---

**V2: Pending vs Filled Orders**
```sql
-- Verify orders are correctly split by status
SELECT 
  'PENDING' as order_type,
  COUNT(*) as count,
  MIN(created_at) as oldest,
  MAX(created_at) as newest
FROM paper_trading_orders
WHERE account_id = 1 AND status = 'PENDING'
UNION ALL
SELECT 
  'FILLED',
  COUNT(*),
  MIN(filled_at),
  MAX(filled_at)
FROM paper_trading_orders
WHERE account_id = 1 AND status = 'FILLED'
UNION ALL
SELECT 
  'CANCELLED',
  COUNT(*),
  MIN(cancelled_at),
  MAX(cancelled_at)
FROM paper_trading_orders
WHERE account_id = 1 AND status = 'CANCELLED';
```

**Expected:** Pending < 20, Filled/Cancelled < 500  
**Bug Symptom:** Pending = 500+ (means FILLED orders weren't filtered on backend)

---

**V3: Lifecycle State Health**
```sql
-- Verify lifecycle_state values are valid and sensible
SELECT 
  lifecycle_state,
  status,
  COUNT(*) as count,
  MAX(updated_at) as most_recent
FROM paper_trading_positions
WHERE account_id = 1
GROUP BY lifecycle_state, status
ORDER BY count DESC;
```

**Expected:** 
```
lifecycle_state | status | count | most_recent
OPEN_POSITION | OPEN | 2 | 2026-05-18 14:45
MARKET_CLOSED_WAITING | OPEN | 1 | 2026-05-18 15:30
```

**Bug Symptom:** `lifecycle_state = "CANCELLED"` with `status = "OPEN"` (state mismatch)

---

**V4: Position vs Trade History Consistency**
```sql
-- Verify that if position is closed, there's a trade history row
SELECT 
  (SELECT COUNT(*) FROM paper_trading_positions 
   WHERE account_id=1 AND status='OPEN') as open_positions,
  (SELECT COUNT(*) FROM paper_trading_trade_history 
   WHERE account_id=1) as total_trades,
  (SELECT COUNT(DISTINCT symbol) FROM paper_trading_positions 
   WHERE account_id=1 AND status='OPEN') as unique_open_symbols,
  (SELECT COUNT(DISTINCT symbol) FROM paper_trading_trade_history 
   WHERE account_id=1) as unique_traded_symbols;
```

**Expected:** open_positions + total_trades = all positions ever entered  
**Bug Symptom:** Position missing from both tables (lost data)

---

**V5: Cash Balance Audit**
```sql
-- Verify cash balance matches accounting
WITH account_summary AS (
  SELECT 
    cash_balance as current_balance,
    starting_balance
  FROM paper_trading_accounts
  WHERE id = 1
),
invested_summary AS (
  SELECT 
    COALESCE(SUM(qty * avg_entry_price), 0) as invested_in_positions
  FROM paper_trading_positions
  WHERE account_id = 1 AND status = 'OPEN'
),
pnl_summary AS (
  SELECT 
    COALESCE(SUM(pnl), 0) as realized_pnl
  FROM paper_trading_trade_history
  WHERE account_id = 1
)
SELECT 
  a.current_balance,
  a.starting_balance,
  i.invested_in_positions,
  p.realized_pnl,
  (a.starting_balance + p.realized_pnl - i.invested_in_positions) as expected_balance,
  CASE 
    WHEN a.current_balance = (a.starting_balance + p.realized_pnl - i.invested_in_positions)
    THEN '✅ CONSISTENT'
    ELSE '❌ MISMATCH: $' || (a.current_balance - (a.starting_balance + p.realized_pnl - i.invested_in_positions))
  END as verification
FROM account_summary a, invested_summary i, pnl_summary p;
```

**Expected:** `✅ CONSISTENT`  
**Bug Symptom:** `❌ MISMATCH` means transaction wasn't recorded or position wasn't updated

---

**V6: Stale Lifecycle States**
```sql
-- Find positions/orders that are paused but should have resumed
SELECT 
  'position' as entity_type,
  id,
  symbol,
  lifecycle_state,
  updated_at,
  datetime('now') as current_time,
  datetime(updated_at, '+1 hour') as was_updated_over_1h_ago
FROM paper_trading_positions
WHERE account_id = 1
  AND lifecycle_state IN ('MARKET_CLOSED_WAITING', 'ERROR_RETRYING', 'TOKEN_EXPIRED_PAUSED')
  AND updated_at < datetime('now', '-1 hour')  -- Hasn't updated in 1+ hour
UNION ALL
SELECT 
  'order' as entity_type,
  id,
  symbol,
  lifecycle_state,
  updated_at,
  datetime('now'),
  datetime(updated_at, '+1 hour')
FROM paper_trading_orders
WHERE account_id = 1
  AND status = 'PENDING'
  AND lifecycle_state IN ('MARKET_CLOSED_WAITING', 'ERROR_RETRYING', 'TOKEN_EXPIRED_PAUSED')
  AND updated_at < datetime('now', '-1 hour');
```

**Expected:** Empty result (should have resumed by now)  
**Bug Symptom:** Returns rows (paused state stuck; engine crashed?)

---

### 8.2 Verification Checklist (Before Deploying Fix)

Run these 6 queries in order:

1. **V1:** Do today's positions exist? ✅ Must show rows
2. **V2:** Are pending/filled orders correctly counted? ✅ Pending << Filled
3. **V3:** Are lifecycle states valid? ✅ No impossible combinations
4. **V4:** Is trade history consistent? ✅ Closed positions in history
5. **V5:** Does cash balance audit? ✅ Must show CONSISTENT
6. **V6:** Any stale paused states? ✅ Must be empty

If any query fails, fix indicates which layer has the bug.

---

## 9. RECOMMENDED IMPLEMENTATION ORDER

### Phase 1: Backend Query Refactor (2-3 days)
**Goal:** Clean separation of active vs historical queries

1. **Step 1:** Define 5 query functions
   - `_get_open_positions(account_id)`
   - `_get_pending_orders(account_id)`
   - `_get_order_history(account_id, limit=100)`
   - `_get_trade_history(account_id, limit=50)`
   - `_get_account_summary(account_id)`

2. **Step 2:** Add query result caching layer
   - Positions/orders: 5-second cache
   - History: 30-second cache
   - Account summary: 10-second cache

3. **Step 3:** Verify consistency
   - Run V1-V6 SQL queries after each function
   - Confirm no data is lost

**Deliverable:** Query functions tested, returning correct filtered results

---

### Phase 2: Response Schema Extension (1-2 days)
**Goal:** Expose lifecycle_state and price metadata

1. **Step 1:** Extend response models
   - Add `lifecycle_state`, `paused_reason`, `monitor_enabled` to position/order responses
   - Add price metadata: `price_source`, `price_fetched_at`, `price_age_seconds`, `is_price_stale`

2. **Step 2:** Update serializers
   - `_serialize_position()` includes new fields
   - `_serialize_order()` includes new fields
   - `_serialize_trade()` as-is (no lifecycle)

3. **Step 3:** Calculate derived fields at response time
   - `price_age_seconds = (now - price_fetched_at).seconds()`
   - `is_price_stale = price_age_seconds > STALE_THRESHOLD`
   - `is_actively_monitored = (lifecycle_state in ACTIVE_STATES) AND monitor_enabled`

**Deliverable:** Response models include new fields with correct values

---

### Phase 3: Route Refactor (2-3 days)
**Goal:** Split dashboard into tab-specific endpoints

1. **Step 1:** Create new routes
   - `GET /paper-trading/positions` → calls `_get_open_positions()`
   - `GET /paper-trading/orders/pending` → calls `_get_pending_orders()`
   - `GET /paper-trading/orders/history` → calls `_get_order_history()`
   - `GET /paper-trading/trades` → calls `_get_trade_history()`
   - `GET /paper-trading/account` → calls `_get_account_summary()`

2. **Step 2:** Keep `/paper-trading/dashboard` for backward compatibility
   - Calls all 5 routes internally
   - Returns composite response
   - Cache: 5 seconds (fastest sub-endpoint)

3. **Step 3:** Document API contract
   - OpenAPI spec updated
   - Frontend docs updated

**Deliverable:** All routes working independently; dashboard still works as fallback

---

### Phase 4: Frontend Refactor (3-4 days)
**Goal:** Use new endpoints; display lifecycle/price metadata

1. **Step 1:** Update API client
   - Add `fetchPaperPositions()`, `fetchPaperOrders()`, etc.
   - Remove old `fetchPaperTradingDashboard()` reliance

2. **Step 2:** Update tab components
   - Positions tab: Calls `fetchPaperPositions()` every 5 seconds
   - Open Orders tab: Calls `fetchPaperOrders()` every 5 seconds
   - History tab: Calls `fetchPaperTrades()` every 30 seconds
   - Account tab: Calls `fetchPaperAccount()` every 10 seconds

3. **Step 3:** Add visual indicators
   - Price staleness: Gray out if > 5 seconds old
   - Lifecycle state: Icons/badges for PAUSED, WAITING, ERROR
   - Paused reason: Tooltip on hover

4. **Step 4:** Add debugging UI (optional)
   - Show `price_source` and `price_fetched_at` in dev tools
   - Show `lifecycle_state` and `paused_reason` in dev tools

**Deliverable:** Tabs display correct data with visual state indicators

---

### Phase 5: Testing & Verification (1-2 days)
**Goal:** Verify all data paths work end-to-end

1. **Step 1:** Run verification queries (V1-V6)
2. **Step 2:** Test scenarios:
   - Buy position → appears in Positions tab
   - Close position → appears in History tab, removed from Positions
   - Market close → positions gray out, resume on open
   - Token refresh → positions resume
3. **Step 3:** Performance testing:
   - Dashboard load time (should be <500ms)
   - Tab switch time (should be <100ms)

**Deliverable:** All scenarios pass; no data corruption

---

## 10. FINAL ARCHITECTURE RECOMMENDATION

### 10.1 Executive Summary

**Problem:** Current system mixes active and historical data in one response, lacks state visibility, missing price metadata → user confusion about position status.

**Solution:** Split reads by use case (active vs historical), expose full state information (lifecycle, pause reason, price freshness), separate by tab for independent polling.

### 10.2 Core Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Separate query functions per data type** | Clear source of truth; prevents mixing PENDING with FILLED orders |
| **Expose lifecycle_state + paused_reason** | UI can show exactly why something isn't active |
| **Include price metadata (source, age, timestamp)** | User knows if price is stale or fallback-based |
| **Tab-specific endpoints** | Each tab can poll at optimal frequency; stale data doesn't persist |
| **Composite dashboard endpoint (legacy)** | Maintains backward compatibility; useful if frontend needs all data at once |
| **Calculate derived fields at response time** | Ensures age_seconds is always current; no stale calculations |
| **Limit history queries (100 rows)** | Prevents response bloat; user doesn't need 5-year history |
| **Keep SQLite (no migration)** | Practical for existing stack; indexes on status/lifecycle_state sufficient |

### 10.3 Correctness Principles

1. **Never mix active with historical in one list**
   - PENDING orders returned separately from FILLED orders
   - OPEN positions never grouped with closed trades
   - Eliminates UI filtering complexity

2. **Every field travels with metadata**
   - Prices include source + age + timestamp
   - States include pause reason
   - Enabling full transparency to user

3. **Source of truth is table + WHERE clause**
   - "Is position open?" → check `paper_trading_positions WHERE status="OPEN"`
   - "Is order filled?" → check `paper_trading_orders WHERE status="FILLED"`
   - No ambiguity

4. **Stale state is detected and surfaced**
   - Price > 5 minutes old → show warning
   - Paused > 1 hour → log error
   - UI can react immediately

### 10.4 Practical Stack Fit

| Component | Fit | Notes |
|-----------|-----|-------|
| FastAPI | ✅ Perfect | Route splitting straightforward; middleware for caching easy |
| SQLite | ✅ Good | Indexes on status/lifecycle_state provide adequate performance; no bottleneck |
| React | ✅ Perfect | Tab-based UI naturally maps to endpoint splitting; independent polling simple |
| Existing DB Schema | ✅ Compatible | No schema changes needed; just add indexes |

### 10.5 Performance Expectations

| Query | Data Size | Load Time | Cache |
|-------|-----------|-----------|-------|
| `_get_open_positions()` | <100 rows | <50ms | 5 sec |
| `_get_pending_orders()` | <50 rows | <30ms | 5 sec |
| `_get_order_history()` | 100 rows | <50ms | 30 sec |
| `_get_trade_history()` | 50 rows | <50ms | 30 sec |
| `_get_account_summary()` | 1 summary | <100ms | 10 sec |
| Full `/dashboard` | all above | <300ms | 5 sec |

**Conclusion:** No performance issues; splitting actually improves responsiveness.

---

## 11. APPENDIX: Migration Checklist

- [ ] **Define 5 query functions** (backend/app/services/paper_trading_service.py)
- [ ] **Add caching layer** (optional: use functools.lru_cache or manual cache)
- [ ] **Extend response schemas** (backend/app/schemas/paper_trading.py)
- [ ] **Update serializers** (backend/app/services/paper_trading_service.py)
- [ ] **Create tab-specific routes** (backend/app/routes/paper_trading.py)
- [ ] **Update OpenAPI docs** (auto-generated from FastAPI)
- [ ] **Update frontend API client** (frontend/src/api.ts)
- [ ] **Update tab components** (frontend/src/components/PaperTradingPage.tsx)
- [ ] **Add visual indicators** (lifecycle icons, price staleness warnings)
- [ ] **Run V1-V6 verification queries** (database verification)
- [ ] **Test all scenarios** (buy, close, market close, token refresh)
- [ ] **Performance test** (load time, memory usage)
- [ ] **Documentation update** (README, API docs)

---

## 12. NEXT STEPS

1. **Review this architecture** → Confirm it matches your vision
2. **Finalize endpoint naming** → Adjust if needed (e.g., `/api/v2/paper-trading/...`)
3. **Design caching strategy** → Decide on Redis vs in-memory vs time-based
4. **Create detailed schema specs** → Include all fields for each endpoint
5. **Begin Phase 1** → Implement query functions

**Ready to code?** Once approved, I'll generate implementation code following this architecture exactly.

---

**Architecture Document Version:** 1.0  
**Date Created:** May 18, 2026  
**Status:** 🔵 READY FOR REVIEW  
**Next Action:** User approval → Code generation

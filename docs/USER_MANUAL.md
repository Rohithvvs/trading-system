# 🗺️ Your Complete Journey — How to Use This App Step by Step

> Read this first. This walks you through the entire application from opening it for the first time to placing your first paper trade.

---

## 🔰 Before You Start — Prerequisites

What you need before using the app:
1. ✅ A Fyers trading account, free to open at fyers.in
2. ✅ Your Fyers access key, generated from the Fyers developer dashboard
3. ✅ A stable internet connection
4. ✅ The app URL, either your deployed link or localhost

**Why do you need a Fyers access key?**
The app uses Fyers to fetch real NSE stock price data. Without the access key, it cannot get fresh prices, candles, scanner results, or live paper-trading quotes. It is like a key to open the data door.

---

## 🚀 Day 1 — First Time Setup (Do This Once)

### Step 1 — Open the Application
- What you see first: the Home screen with Market Overview, Saved Scans, Scan History, Alerts, and Admin panels.
- Where to go first: use the top navigation to move between Scanner, Home, and Paper Trading.
- Screenshot description: a workstation-style dashboard with cards for market status, saved scanner setups, recent scan snapshots, alerts, risk settings, and service health.

### Step 2 — Connect Your Fyers Account
- Go to Paper Trading → Account → FYERS Access Key.
- Paste your Fyers access key into the Access key field.
- Click Save Access Key.
- A successful save shows Access Key Active ✅ and updates the access key history table.
- If the access key is wrong, too short, expired, or inactive, the app may show an error, inactive status, or scanner failure.
- Real example: Go to Paper Trading → Account → paste your access key → click Save Access Key → you will see a green active status confirming connection.

### Step 3 — Run Your First Scan
- Go to Scanner.
- Timeframe means candle size. 1d means one daily candle.
- Lookback means how much history the app checks. 180 means the last 180 candles.
- Top Set means how many top-ranked stocks get deeper analysis. 20 means show the top 20 final candidates.
- Click Run Nifty 500 Swing Scanner.
- The scan can take a few minutes.
- While scanning, the app shows a loading panel explaining that it is fetching price history, checking data quality, and scoring stocks.
- Real example: Click Run Nifty 500 Swing Scanner → wait 2-3 minutes → results appear in the table below.

### Step 4 — Read the Scanner Results
- Start with the summary cards: Total scanned, Data valid, Broad trend matched, Shortlisted, BUY candidates, WATCH candidates, and Rejected.
- BUY candidate means ready to review for a possible trade now.
- WATCH candidate means promising, but wait for cleaner confirmation.
- Matched means it passed scanner checks but may not be one of the top final BUY or WATCH ideas.
- Score numbers are like a credit score for stock health. Higher is usually stronger.
- Real example: If HINDZINC shows score 95 in BUY, it means the stock passed many checks and is one of the strongest setups today.

### Step 5 — Click on a Stock to Analyse It
- Click a stock row in the Candidate Decision Table.
- The app opens the Stock Detail page.
- Read tabs in this order: Overview → Technicals → Trade Plan → News → Backtest → Chart.
- Real example: Click HINDZINC → you land on the detail page → first read Overview to understand the recommendation.

### Step 6 — Read the Overview Tab
- Read the recommendation summary and risk warnings.
- Bullish posture means the app sees an upward-friendly setup.
- Final Score combines chart strength, news, backtest, and trade quality.
- Technical Score focuses mainly on chart health.
- A Final Score of 67 with Technical Score of 95 means the chart is strong, but other support may be weaker.
- Real example: HINDZINC shows Final Score 85, Technical 95, News neutral. The chart picture is strong, but news is not adding much support yet.

### Step 7 — Check the Technicals Tab
- Read the Trade Confidence Checklist first.
- PASS means that check supports the trade.
- CHECK means pause and review before entering.
- Review EMA20, Supertrend, MACD, RSI, SMA trend, structure, volume, ATR, Bollinger, and multi-timeframe cards.
- Real example: If EMA20 shows Passed and price is ₹1,560 versus EMA20 at ₹1,415, price is comfortably above the trend line.

### Step 8 — Read the Trade Plan Tab
- Entry zone tells you where buying may make sense.
- Stop loss is the safety net below the trade.
- Target 1 and Target 2 are possible profit areas.
- Risk/Reward compares possible gain with possible loss.
- Position sizing tells you quantity based on your risk amount.
- Holding horizon tells you how long the trade may need.
- Real example: Entry ₹1,543-₹1,570, Stop Loss ₹1,482, Target ₹1,651 means buy inside that price range, exit if price falls to ₹1,482, and aim for ₹1,651 first.

### Step 9 — Check the News Tab
- News matters because bad news can break a good-looking chart.
- Positive sentiment supports the setup.
- Neutral sentiment means news is not helping or hurting much.
- Negative sentiment is a warning to slow down or skip.
- Real example: Before buying HINDZINC, check if there is bad news about zinc prices, company results, or promoter selling. If news is negative, skip even if technicals are good.

### Step 10 — Check the Backtest Tab
- Backtest means replaying past market data to see how this trading idea would have behaved.
- Win Rate shows how many past trades made money.
- Max Drawdown shows the worst fall during the test.
- Equity Curve shows whether results grew smoothly or with painful drops.
- Real example: Win Rate 62%, Max Drawdown 18% means this style won 62 out of 100 past trades, and the worst rough patch was about 18%.

### Step 11 — Place a Paper Trade
- Go to Paper Trading.
- Use the Order Ticket on the right side.
- Fill symbol, side, type, quantity, price, stop loss, target, and notes.
- Click Place Order.
- Track open positions in the Positions tab.
- Close a position when target hits, stop loss hits, or the idea is no longer valid.
- Real example: Buy 10 shares of HINDZINC at ₹500 paper trade → set stop loss ₹470 and target ₹550 → when price hits ₹550, close the position → P&L shows +₹500 profit.

---

## 📅 Daily Routine — How to Use This App Every Day

### Morning Routine (9:15 AM - 9:30 AM)
1. Open the app.
2. Check if the Fyers access key is still active.
3. Run the scanner after 9:20 AM.
4. Review BUY and WATCH candidates.
5. Open detail page for each candidate.
6. Check Trade Plan for entry zone.
7. Decide which setups to track.

### During Market Hours
1. Monitor paper trade positions.
2. Check if price reaches entry zone.
3. Check if stop loss is hit.
4. Check if target is hit, then close position.

### Evening Review (3:30 PM - 4:00 PM)
1. Run scanner again for next-day setups.
2. Review backtest results for any new strategy.
3. Note which setups triggered and which did not.

---

## ⚠️ Common Mistakes to Avoid

1. Running scanner before market opens, because data may be outdated.
2. Ignoring stop loss levels.
3. Entering a stock without checking News tab.
4. Taking too many positions at once.
5. Not checking Risk/Reward. Avoid trades below 1:1.5.

---

# 📱 Home / Workstation

> The Home screen is your control room for market overview, saved scans, scan history, alerts, risk settings, and app health.

---

## 🗂️ Section: Market Overview

**What this section does:**
This section shows the broad market picture before you scan or trade. It gives you index cards, VIX information when available, top scan scores, and lowest scan scores.

**Real-life example:**
Think of this like checking the weather before leaving home. If the market looks stormy, you may carry an umbrella by reducing trade size or skipping weak setups.

### Features in this section:

#### ✅ Refresh Market Overview
- **What it does:** Updates the Home screen cards with the latest available market and scan summary.
- **Where to find it:** Home → Market Overview → Refresh.
- **How to use it:** Click Refresh. Wait for the cards to reload. Read the updated index and score lists.
- **Example:** If NIFTY is strong and RELIANCE has a high score near 88, open Scanner and look for more BUY candidates.

#### ✅ Top and Lowest Scan Scores
- **What it does:** Shows stronger and weaker names from recent scan data.
- **Where to find it:** Home → Market Overview → Top scan scores and Lowest scan scores.
- **How to use it:** Start with top scores for possible ideas. Treat lowest scores as avoid-or-wait names.
- **Example:** BHARATFORG at score 8.5 may deserve review, while RELIANCE at -4.0 may need patience.

---

## 🗂️ Section: Saved Scans

**What this section does:**
Saved Scans lets you reuse scanner settings instead of entering them again every day. It remembers universe, timeframe, lookback, top set, and filters.

**Real-life example:**
Think of this like saving a Zomato filter for “South Indian, under ₹300, near me” so you do not rebuild the same search every time.

### Features in this section:

#### ✅ Load Saved Scan
- **What it does:** Loads a saved scanner setup into the Scanner screen.
- **Where to find it:** Home → Saved Scans → Load.
- **How to use it:** Find the saved scan. Click Load. Run the scanner with those settings.
- **Example:** Load “NIFTY500 daily swing” with 1d, lookback 180, top 20.

#### ✅ Delete Saved Scan
- **What it does:** Removes a saved setup you no longer use.
- **Where to find it:** Home → Saved Scans → Delete.
- **How to use it:** Pick the scan. Click Delete. Confirm it disappears.
- **Example:** Delete an old “4h test scan” if you now only use daily swing scans.

---

## 🗂️ Section: Scan History

**What this section does:**
Scan History shows previous scanner snapshots stored by the app. It helps you compare what changed between scans.

**Real-life example:**
Think of this like checking yesterday’s cricket team sheet before today’s match. You can see who entered, who left, and who stayed.

### Features in this section:

#### ✅ Server Snapshots
- **What it does:** Lists previous scan runs with shortlist, BUY count, WATCH count, and data source.
- **Where to find it:** Home → Scan History.
- **How to use it:** Read timestamp and counts. Use it to judge whether market setups are improving.
- **Example:** Yesterday had 3 BUY candidates and today has 12, so swing setups may be improving.

#### ✅ Compare Scan
- **What it does:** Shows new, removed, and stayed symbols compared with another scan.
- **Where to find it:** Home → Scan History → Compare.
- **How to use it:** Click Compare. Read New, Removed, and Stayed. Review newly added names first.
- **Example:** HINDZINC appears in New, BHARATFORG stayed, and RELIANCE was removed.

---

## 🗂️ Section: Alerts

**What this section does:**
Alerts help you remember important price levels or scan-entry ideas. They are useful when you do not want to stare at charts all day.

**Real-life example:**
Think of this like setting an alarm for milk on the stove. The app nudges you when a price condition matters.

### Features in this section:

#### ✅ Price Alert
- **What it does:** Creates an alert when a symbol moves above or below your chosen price.
- **Where to find it:** Home → Alerts → Price alert.
- **How to use it:** Enter name, symbol, condition, and target price. Click Create price alert.
- **Example:** Create HINDZINC above ₹500 so you know when it reaches your entry area.

#### ✅ Scan-Entry Alert
- **What it does:** Creates an alert linked to a scan idea.
- **Where to find it:** Home → Alerts → Scan-entry alert.
- **How to use it:** Enter alert name. Click Create scan alert. Review it in the alert list.
- **Example:** Create “NIFTY500 BUY list” for daily scan-entry tracking.

#### ✅ Delete Alert
- **What it does:** Removes an alert you no longer need.
- **Where to find it:** Home → Alerts list → Delete.
- **How to use it:** Find the alert. Click Delete. Confirm it is gone.
- **Example:** Delete a RELIANCE ₹2,900 alert after cancelling the idea.

---

## 🗂️ Section: Risk and App Health

**What this section does:**
This section lets you choose a broad risk style and check whether the app’s main services are healthy. It also shows stored data size and service status.

**Real-life example:**
Think of this like checking your car dashboard before a long drive. Fuel, engine light, and tyre pressure matter before speed.

### Features in this section:

#### ✅ Risk Profile
- **What it does:** Sets your risk style: conservative, moderate, or aggressive.
- **Where to find it:** Home → Admin → Risk profile.
- **How to use it:** Choose profile. Enter position size percent and max risk percent. Click Save risk.
- **Example:** Moderate with max risk 2% means ₹20,000 max risk on ₹10 lakh capital.

#### ✅ App Health
- **What it does:** Shows whether important app services are working.
- **Where to find it:** Home → Admin → service health panel.
- **How to use it:** Read each status. Pause trading decisions if a data service is failing.
- **Example:** If data connection status fails, HINDZINC prices may not refresh correctly.

---

# 📱 Scanner / Dashboard

> The Scanner screen checks a universe like NIFTY500 and turns hundreds of stocks into a short, trade-ready list.

---

## 🗂️ Section: Scanner Controls

**What this section does:**
This section controls how the scan runs. You choose chart timeframe, universe, lookback period, and top set size before starting.

**Real-life example:**
The scanner is like a Zomato filter. Instead of showing every restaurant, it shows only the stocks that match your recipe.

### Features in this section:

#### ✅ Market Status
- **What it does:** Shows whether the market is open or closed.
- **Where to find it:** Scanner header → Market card.
- **How to use it:** Check it before scanning. Prefer scanning after market data starts updating.
- **Example:** If Market shows Closed at 8:00 AM, wait until after 9:20 AM for fresh HINDZINC signals.

#### ✅ Last Scan Time
- **What it does:** Shows when the scanner last produced results.
- **Where to find it:** Scanner header → Last scan card.
- **How to use it:** If it is old, run a new scan. If it says restored, treat it as previous data.
- **Example:** A scan from yesterday at 3:45 PM should be refreshed today.

#### ✅ Timeframe
- **What it does:** Chooses candle size: 1h, 4h, or 1d.
- **Where to find it:** Scanner header → Timeframe.
- **How to use it:** Select 1d for swing trades. Click Run Nifty 500 Swing Scanner.
- **Example:** Use 1d to study RELIANCE daily candles around ₹2,850.

#### ✅ Universe
- **What it does:** Chooses which stock list the scanner checks.
- **Where to find it:** Scanner header → Universe.
- **How to use it:** Pick NIFTY500 or another list. Confirm the count in brackets. Run the scan.
- **Example:** NIFTY500 (500) checks roughly 500 NSE stocks.

#### ✅ Lookback
- **What it does:** Controls how much past price history the scan studies.
- **Where to find it:** Scanner header → Lookback.
- **How to use it:** Enter 60 to 365. Use 180 as a balanced default.
- **Example:** Lookback 180 checks about 180 daily candles for BHARATFORG near ₹1,250.

#### ✅ Top Set
- **What it does:** Controls how many top-ranked stocks get deeper analysis.
- **Where to find it:** Scanner header → Top set.
- **How to use it:** Enter 5 to 50. Use 20 for a manageable daily list.
- **Example:** Top set 20 means the app deeply reviews the best 20 names from NIFTY500.

#### ✅ Run Nifty 500 Swing Scanner
- **What it does:** Starts the full scan and creates BUY, WATCH, and rejected results.
- **Where to find it:** Scanner header → primary button.
- **How to use it:** Check settings. Click Run Nifty 500 Swing Scanner. Wait for results.
- **Example:** Run 1d, lookback 180, top 20. HINDZINC appears as BUY with score 92.

#### ✅ Theme Toggle and Notification Bell
- **What it does:** Switches light/dark mode and shows recent notifications.
- **Where to find it:** Scanner header → Light mode/Dark mode and bell icon.
- **How to use it:** Toggle theme for comfort. Check notifications for paper-trading updates.
- **Example:** A bell message says RELIANCE target touched ₹2,950, so review the paper trade.

---

## 🗂️ Section: Scan Summary

**What this section does:**
These cards summarize the entire scan in one row. They tell you how much data was usable and how many stocks survived each filter.

**Real-life example:**
Think of it like an exam result summary: total students, passed students, top rankers, and students who need improvement.

### Features in this section:

#### ✅ Total Scanned
- **What it does:** Shows how many stocks the scanner tried to check.
- **Where to find it:** Scanner → first summary card.
- **How to use it:** Confirm the number matches your universe. If it is too low, check the Fyers access key.
- **Example:** Total scanned 500 means NIFTY500 was checked.

#### ✅ Data Valid
- **What it does:** Shows how many stocks had enough clean price history.
- **Where to find it:** Scanner → Data valid card.
- **How to use it:** Compare it with Total scanned. If many are missing, update access key or adjust lookback.
- **Example:** 247 valid out of 755 means only 247 had usable data, so be careful.

#### ✅ Broad Trend Matched
- **What it does:** Shows how many stocks passed the broad trend gate.
- **Where to find it:** Scanner → Broad trend matched card.
- **How to use it:** Use it to judge overall market health.
- **Example:** 120 matched from 500 means many NSE stocks are in constructive trend.

#### ✅ Shortlisted, BUY, WATCH, Rejected
- **What it does:** Shows how many names reached each final bucket.
- **Where to find it:** Scanner → summary cards.
- **How to use it:** Review BUY first, WATCH second, rejected only for learning.
- **Example:** 20 shortlisted, 4 BUY, 8 WATCH, 8 rejected gives a focused review list.

---

## 🗂️ Section: Filters and Results

**What this section does:**
Filters narrow the result table so you can focus. The table shows signal, score, confidence, trade levels, trend, momentum, volume, news, and last update.

**Real-life example:**
Think of it like filtering products on Amazon. You do not want everything, only the choices that fit your budget and quality.

### Features in this section:

#### ✅ Signal Filter
- **What it does:** Shows ALL, BUY, WATCH, or REJECT rows.
- **Where to find it:** Scanner → Candidate filters → Signal.
- **How to use it:** Click BUY for actionable names. Click WATCH for tracking names. Click ALL to reset.
- **Example:** Select BUY to see only HINDZINC and other current buy ideas.

#### ✅ Score Range
- **What it does:** Shows only stocks inside your chosen score range.
- **Where to find it:** Scanner → Candidate filters → Score.
- **How to use it:** Enter minimum and maximum. Use 70 to 100 for stronger setups.
- **Example:** Set 80-100 to focus on BHARATFORG with score 87.

#### ✅ Sort, Search, and High Confidence
- **What it does:** Sorts rows, finds symbols, and filters for stronger confidence.
- **Where to find it:** Scanner → Candidate filters.
- **How to use it:** Sort by Rank, Score, Confidence, or Risk/Reward. Search RELIANCE-EQ. Tick Only high-confidence setups.
- **Example:** Sort by Risk/Reward and find HINDZINC at 2.1 versus RELIANCE at 1.2.

#### ✅ Candidate Decision Table
- **What it does:** Shows the main shortlist with trade-ready columns.
- **Where to find it:** Scanner → Shortlisted view.
- **How to use it:** Read Rank and Signal first. Check score, entry, stop loss, and Risk/Reward. Click a row for details.
- **Example:** HINDZINC rank #1, BUY, score 95, entry ₹500-₹510, stop ₹470, target ₹550.

#### ✅ All Analyzed Table
- **What it does:** Shows every analyzed stock, including passed and rejected names.
- **Where to find it:** Scanner → All Analyzed.
- **How to use it:** Read status and rejection reason to learn why a stock failed.
- **Example:** RELIANCE shows Failed because price is below EMA20, so it is not ready.

#### ✅ Save Scan and Export CSV
- **What it does:** Saves scanner settings or downloads results.
- **Where to find it:** Scanner → Save scan name, Save Scan, Export CSV.
- **How to use it:** Name the setup and save it. Export after a scan if you want spreadsheet review.
- **Example:** Save “Daily NIFTY500 swing” and export HINDZINC, BHARATFORG, RELIANCE rows.

#### ✅ Loading, Error, and Retry
- **What it does:** Shows scanner progress and lets you retry after failure.
- **Where to find it:** Scanner results area.
- **How to use it:** Wait during scanning. If Fyers rate limit appears, wait 60 seconds and click Retry scan.
- **Example:** If the access key expired, update it in Paper Trading → Account before retrying.

---

# 📱 Stock Detail Page

> The Stock Detail page explains one selected stock from every angle: recommendation, technicals, trade plan, news, backtest, and chart.

---

## 🗂️ Section: Header and Navigation

**What this section does:**
The header summarizes the selected stock with signal, score, confidence, Risk/Reward, rank, and readiness. Tabs let you move through the full review.

**Real-life example:**
Think of this as the front page of a medical report. It does not replace the full report, but it tells you whether the patient looks healthy.

### Features in this section:

#### ✅ Back to Scan Results
- **What it does:** Returns you to the scanner table.
- **Where to find it:** Top-left of Stock Detail page.
- **How to use it:** Click Back to scan results. Pick another stock.
- **Example:** After reading HINDZINC, go back and open BHARATFORG.

#### ✅ Header Metrics
- **What it does:** Shows score, confidence, Risk/Reward, rank, and readiness.
- **Where to find it:** Stock Detail header.
- **How to use it:** Read Score and Risk/Reward first, then continue to Trade Plan.
- **Example:** Score 88, Confidence 78%, Risk/Reward 2.0 is stronger than score 55.

#### ✅ Send to Paper Trading
- **What it does:** Sends BUY or WATCH trade levels into the paper-trading order ticket.
- **Where to find it:** Stock Detail toolbar, visible for BUY or WATCH stocks.
- **How to use it:** Click Send to paper trading. Review the filled ticket before placing.
- **Example:** Send HINDZINC with entry around ₹505, stop ₹470, target ₹550.

---

## 🗂️ Section: Overview Tab

**What this section does:**
Overview explains the recommendation in plain language. It shows top reasons, risk warnings, company information, score breakdown, 52-week range, confidence, and data quality.

**Real-life example:**
Think of Overview like reading the first page of a loan application: score, background, reasons, and risks are all in one place.

### Features in this section:

#### ✅ Recommendation Overview
- **What it does:** Explains why the stock is being considered.
- **Where to find it:** Stock Detail → Overview → Recommendation overview.
- **How to use it:** Read summary, Top reasons, and Risk warnings before acting.
- **Example:** HINDZINC may have strong trend and momentum, but weak news support.

#### ✅ Company Information
- **What it does:** Shows sector, industry, and market cap when available.
- **Where to find it:** Stock Detail → Overview → info cards.
- **How to use it:** Check what business the stock belongs to and avoid overloading one sector.
- **Example:** HINDZINC is metals, while RELIANCE is a large diversified company.

#### ✅ Score Breakdown and Ranking Context
- **What it does:** Shows Final score, Technical score, Scanner score, News score, and rank explanation.
- **Where to find it:** Stock Detail → Overview → Ranking context.
- **How to use it:** Check whether final score is supported by chart and news. Prioritize better-ranked BUY candidates.
- **Example:** Rank #1 HINDZINC with Technical 95 deserves review before rank #18 BHARATFORG.

#### ✅ 52-Week Range, Confidence, and Data Quality
- **What it does:** Shows where price sits in its yearly range, how confident the app is, and whether data is usable.
- **Where to find it:** Stock Detail → Overview.
- **How to use it:** Avoid chasing near highs unless the setup is strong. Skip weak data.
- **Example:** RELIANCE at ₹2,850 near its 52-week high may need tighter risk control.

---

## 🗂️ Section: Technicals Tab

**What this section does:**
Technicals checks chart health using trend, momentum, structure, volatility, volume, and candle behavior. It helps confirm whether the stock has enough technical support.

**Real-life example:**
Think of technical score like a fitness score. One strong muscle is not enough; the whole body should be healthy.

### Features in this section:

#### ✅ Technical Decision
- **What it does:** Shows the technical signal and whether hard checks passed.
- **Where to find it:** Stock Detail → Technicals → Technical decision.
- **How to use it:** Read signal, confirm hard filters passed, and review fail reasons.
- **Example:** HINDZINC bullish with hard filters passed is cleaner than RELIANCE mixed.

#### ✅ ATR, Bollinger, and Multi-Timeframe Cards
- **What it does:** Shows volatility, band position, and daily/weekly alignment.
- **Where to find it:** Stock Detail → Technicals → top metric cards.
- **How to use it:** Reduce quantity for high ATR, avoid stretched Bollinger positions, and prefer daily plus weekly support.
- **Example:** BHARATFORG near upper band at ₹1,280 may need a pullback.

#### ✅ Trade Confidence Checklist
- **What it does:** Turns key chart checks into PASS or CHECK items.
- **Where to find it:** Stock Detail → Technicals → Trade confidence checklist.
- **How to use it:** Treat CHECK as a warning. Continue only when major checks support the trade.
- **Example:** EMA20 PASS, Supertrend PASS, MACD PASS, RSI PASS makes HINDZINC healthier.

#### ✅ Indicator Cards
- **What it does:** Shows EMA20, Supertrend, MACD, RSI, SMA trend, structure, volume, and candle confirmation.
- **Where to find it:** Stock Detail → Technicals → indicator grid.
- **How to use it:** Review each card. Prefer price above EMA20, positive Supertrend, supportive MACD and RSI, and good volume.
- **Example:** Price ₹1,560 above EMA20 ₹1,415 supports HINDZINC trend health.

---

## 🗂️ Section: Trade Plan Tab

**What this section does:**
Trade Plan converts the recommendation into practical trading levels. It shows entry zone, stop loss, targets, Risk/Reward, position sizing, and holding guidance.

**Real-life example:**
Think of this like Google Maps for a trade. It tells you where to enter, where to stop, and where the destination may be.

### Features in this section:

#### ✅ Entry Zone
- **What it does:** Shows the suggested buy range.
- **Where to find it:** Stock Detail → Trade Plan.
- **How to use it:** Wait for price to enter the range. Avoid buying far above it.
- **Example:** HINDZINC entry ₹500-₹510 means avoid chasing at ₹540.

#### ✅ Stop Loss
- **What it does:** Shows the price where the trade idea should be exited if wrong.
- **Where to find it:** Stock Detail → Trade Plan → Stop loss.
- **How to use it:** Place it before entering. Do not move it lower just to avoid loss.
- **Example:** Buy HINDZINC at ₹505 with stop ₹470. Exit if price reaches ₹470.

#### ✅ Target 1 and Target 2
- **What it does:** Shows first and second profit areas.
- **Where to find it:** Stock Detail → Trade Plan.
- **How to use it:** Review at Target 1. Use Target 2 only if momentum remains strong.
- **Example:** Target 1 ₹550 and Target 2 ₹590 on HINDZINC.

#### ✅ Risk/Reward Ratio
- **What it does:** Compares possible profit with possible loss.
- **Where to find it:** Stock Detail → Trade Plan.
- **How to use it:** Prefer 1.5 or higher. Skip weak trades below 1.0.
- **Example:** Entry ₹500, stop ₹470, target ₹560 gives Risk/Reward 2.0.

#### ✅ Position Sizing
- **What it does:** Calculates quantity based on your risk amount.
- **Where to find it:** Stock Detail → Trade Plan → Position sizing.
- **How to use it:** Enter risk amount. Use suggested quantity in Paper Trading.
- **Example:** Risk ₹5,000, entry ₹500, stop ₹470 means about 166 shares.

#### ✅ Holding Horizon
- **What it does:** Shows expected trade timeframe.
- **Where to find it:** Stock Detail → Trade Plan.
- **How to use it:** Use it to avoid exiting too early.
- **Example:** A swing horizon means HINDZINC may take days or weeks, not minutes.

---

## 🗂️ Section: News Tab

**What this section does:**
News shows recent articles, sentiment, and company events when available. It helps you avoid buying into bad headlines.

**Real-life example:**
Think of news like checking traffic before driving. The route may look good, but a roadblock can ruin the trip.

### Features in this section:

#### ✅ Sentiment
- **What it does:** Shows whether recent news is positive, neutral, or negative.
- **Where to find it:** Stock Detail → News.
- **How to use it:** Be cautious with negative sentiment and confirm with headlines.
- **Example:** HINDZINC neutral news means the chart can still work, but news is not a tailwind.

#### ✅ Articles and Corporate Events
- **What it does:** Shows related news and event details when available.
- **Where to find it:** Stock Detail → News.
- **How to use it:** Check for results, sector news, promoter actions, and regulatory events.
- **Example:** If RELIANCE results are tomorrow, use smaller size or wait.

---

## 🗂️ Section: Backtest Tab

**What this section does:**
Backtest shows how the strategy behaved in the past. It includes win rate, return, max drawdown, trade count, Sharpe, profit factor, equity curve, monthly returns, best trade, and worst trade.

**Real-life example:**
Backtest is like replaying last year’s cricket matches to see whether your team’s strategy would have won often enough.

### Features in this section:

#### ✅ Backtest Strength Metrics
- **What it does:** Shows win rate, return, max drawdown, total trades, Sharpe, and profit factor.
- **Where to find it:** Stock Detail → Backtest → Backtest strength.
- **How to use it:** Prefer positive returns, controlled drawdown, enough trades, and profit factor above 1.0.
- **Example:** Win Rate 62%, Max Drawdown 18%, Profit Factor 1.8 is healthier than Profit Factor 0.8.

#### ✅ Equity Curve
- **What it does:** Shows how capital moved over time.
- **Where to find it:** Stock Detail → Backtest → Equity curve.
- **How to use it:** Look for steady upward behavior and avoid curves with huge drops.
- **Example:** A smooth HINDZINC curve is easier to trust than one with repeated deep falls.

#### ✅ Monthly Returns
- **What it does:** Shows month-by-month return tiles.
- **Where to find it:** Stock Detail → Backtest → Monthly returns.
- **How to use it:** Check consistency and avoid setups with too many red months.
- **Example:** Six green months and two small red months is better than one big green month and many red months.

#### ✅ Best and Worst Trade
- **What it does:** Shows the strongest and weakest past trades.
- **Where to find it:** Stock Detail → Backtest.
- **How to use it:** Use it to understand realistic upside and downside.
- **Example:** Best trade +14%, worst trade -7% gives a practical range of outcomes.

---

## 🗂️ Section: Chart Tab

**What this section does:**
Chart shows price candles, EMA20, Supertrend, volume, trade levels, timeframe controls, zoom controls, and hover price details.

**Real-life example:**
Think of the chart like a stock’s heartbeat monitor. It shows rhythm, pressure, and where your planned trade levels sit.

### Features in this section:

#### ✅ Timeframe and Zoom Controls
- **What it does:** Switches between 1D, 1W, 1M and shows fewer or more bars.
- **Where to find it:** Stock Detail → Chart → top controls.
- **How to use it:** Use 1D for detail, 1W for bigger trend, and zoom to inspect recent candles.
- **Example:** Zoom in to inspect the last 10 HINDZINC candles near ₹500.

#### ✅ Candles, EMA20, Supertrend, and Volume
- **What it does:** Shows price action and trend guides.
- **Where to find it:** Stock Detail → Chart.
- **How to use it:** Look for higher highs, higher lows, price above EMA20, and positive Supertrend.
- **Example:** HINDZINC bullish flip near ₹480 can support a BUY setup.

#### ✅ Trade Level Lines and Hover Details
- **What it does:** Draws entry, stop, targets, and shows candle details on hover.
- **Where to find it:** Stock Detail → Chart.
- **How to use it:** Check whether current price is near entry or too close to target. Hover to read OHLC and volume.
- **Example:** If current price is ₹545 and Target 1 is ₹550, do not buy late for only ₹5 upside.

---

# 📱 Paper Trading

> Paper Trading lets you practise buying, selling, tracking P&L, and managing risk without using real money.

---

## 🗂️ Section: Account Summary and Workspace

**What this section does:**
This section shows your virtual account health and the selected stock workspace. It updates prices and P&L so you can practise trade management.

**Real-life example:**
Think of paper trading like a cricket net session. You practise real shots, but the match pressure is removed.

### Features in this section:

#### ✅ Account Metrics
- **What it does:** Shows balance, equity, realized P&L, unrealized P&L, invested amount, available cash, open positions, and open orders.
- **Where to find it:** Top of Paper Trading.
- **How to use it:** Read available cash before placing orders. Watch realized and unrealized P&L.
- **Example:** Starting capital ₹10,00,000, invested ₹50,000, available cash ₹9,50,000.

#### ✅ Selected Symbol and Live Pricing
- **What it does:** Sets the active stock and keeps current price refreshed when available.
- **Where to find it:** Paper Trading workspace and order ticket.
- **How to use it:** Choose or type a symbol. Wait for quote and candles. Leave live pricing on during market hours.
- **Example:** Select HINDZINC-EQ and watch current price move from ₹500 to ₹505.

#### ✅ Offline Gap Replay
- **What it does:** Tells you if orders or exits happened while the app was offline.
- **Where to find it:** Paper Trading status area after opening the screen.
- **How to use it:** Read the banner. Review positions and orders immediately.
- **Example:** If it says one order filled while offline, check your HINDZINC position.

---

## 🗂️ Section: Positions

**What this section does:**
Positions shows every open paper trade. It lets you monitor quantity, entry price, current price, P&L, stop loss, target, and close actions.

**Real-life example:**
Think of this like a school attendance register for your trades. Every open trade is listed and must be accounted for.

### Features in this section:

#### ✅ Open Positions
- **What it does:** Lists active paper trades and their running profit or loss.
- **Where to find it:** Paper Trading → Positions tab.
- **How to use it:** Read symbol, quantity, entry, current price, P&L, stop, and target.
- **Example:** HINDZINC 10 shares, entry ₹500, current ₹525, unrealized P&L +₹250.

#### ✅ Close Position
- **What it does:** Closes a selected open paper position.
- **Where to find it:** Positions table or Trade Details card.
- **How to use it:** Choose the position. Click close or exit action. Confirm it moves to History.
- **Example:** Close HINDZINC at ₹550 for +₹500 on 10 shares.

#### ✅ Square Off All
- **What it does:** Closes all open positions at once.
- **Where to find it:** Paper Trading → Positions → Square off all.
- **How to use it:** Click Square off all. Confirm warning. Review that positions are closed.
- **Example:** Close HINDZINC, BHARATFORG, and RELIANCE paper positions before market close.

---

## 🗂️ Section: Open Orders

**What this section does:**
Open Orders shows pending limit and stop orders that have not filled yet. You can edit, cancel, or delete them.

**Real-life example:**
Think of this like restaurant orders waiting in the kitchen. Some are not served yet, and you can still cancel before they are prepared.

### Features in this section:

#### ✅ Open Orders Table
- **What it does:** Lists pending paper orders.
- **Where to find it:** Paper Trading → Open Orders tab.
- **How to use it:** Review symbol, side, type, quantity, price, stop, target, and status.
- **Example:** HINDZINC BUY LIMIT 10 shares at ₹500 remains pending while price is ₹512.

#### ✅ Edit or Cancel Order
- **What it does:** Changes or cancels a pending order.
- **Where to find it:** Open Orders table → Edit, Cancel, or Delete.
- **How to use it:** Click Edit to load it into the ticket. Click Cancel/Delete to remove it.
- **Example:** Change HINDZINC limit from ₹500 to ₹505, or cancel RELIANCE if news turns negative.

---

## 🗂️ Section: History, Analytics, and Alerts

**What this section does:**
These tabs help you review closed trades, measure practice performance, and create price reminders.

**Real-life example:**
Think of this like a fitness app plus alarm clock. It tracks your progress and reminds you when something important happens.

### Features in this section:

#### ✅ Trade History
- **What it does:** Shows completed trades with entry, exit, P&L, holding period, and exit reason.
- **Where to find it:** Paper Trading → History tab.
- **How to use it:** Review closed trades and check whether you followed stop and target rules.
- **Example:** HINDZINC entry ₹500, exit ₹550, P&L +₹500, exit reason target hit.

#### ✅ Analytics
- **What it does:** Summarizes paper-trading performance with charts and numbers.
- **Where to find it:** Paper Trading → Analytics tab.
- **How to use it:** Review total P&L, daily behavior, and holding patterns.
- **Example:** If five RELIANCE breakout trades lose money, reduce that setup size.

#### ✅ Price Alerts
- **What it does:** Creates and lists paper-trading price alerts.
- **Where to find it:** Paper Trading → Alerts tab.
- **How to use it:** Enter symbol, condition, and price. Click Set Alert. Delete old alerts when done.
- **Example:** Set HINDZINC-EQ price ≤ ₹470 to warn near stop loss.

---

## 🗂️ Section: Account

**What this section does:**
Account shows your paper capital, lets you change starting capital, reset the account, review transactions, and manage your Fyers access key.

**Real-life example:**
Think of this like your practice trading bank passbook plus key locker.

### Features in this section:

#### ✅ Account Summary
- **What it does:** Shows starting capital, current total capital, available funds, margin used, realized P&L, and unrealized P&L.
- **Where to find it:** Paper Trading → Account → Summary.
- **How to use it:** Review capital before trading and avoid overusing available funds.
- **Example:** Starting ₹10,00,000 and realized P&L +₹12,000 means practice results improved.

#### ✅ Set Starting Capital and Reset Account
- **What it does:** Changes starting capital or resets all paper-trading activity.
- **Where to find it:** Paper Trading → Account → Account Settings.
- **How to use it:** Enter capital and Save, or click Reset Account when you want a clean slate.
- **Example:** Set ₹5,00,000 if that matches your real planned capital.

#### ✅ Transaction Log
- **What it does:** Shows money movement from paper orders, exits, and resets.
- **Where to find it:** Paper Trading → Account → Transactions.
- **How to use it:** Review date, symbol, action, amount, and balance after.
- **Example:** HINDZINC SELL shows +₹5,500 after closing at target.

#### ✅ Fyers Access Key Status, Save, and History
- **What it does:** Shows, saves, and tracks your Fyers access key.
- **Where to find it:** Paper Trading → Account → FYERS Access Key.
- **How to use it:** Paste a new access key, click Save Access Key, and confirm Access Key Active ✅.
- **Example:** Update the key before scanning HINDZINC and RELIANCE after an expiry.

---

## 🗂️ Section: Order Ticket, Paper Chart, and Trade Details

**What this section does:**
This area is where you create paper orders, see your planned levels on a chart, and adjust stop loss or target for open trades.

**Real-life example:**
Think of it like a railway ticket form plus route map. Review the destination, risk, and path before submitting.

### Features in this section:

#### ✅ Order Ticket
- **What it does:** Creates or updates a paper order.
- **Where to find it:** Paper Trading → right side Order Ticket.
- **How to use it:** Fill symbol, BUY/SELL, type, quantity, price, stop loss, target, and notes. Click Place Order.
- **Example:** Place HINDZINC BUY LIMIT 10 shares at ₹500 with stop ₹470 and target ₹550.

#### ✅ Risk Preview
- **What it does:** Shows estimated cost, risk amount, reward amount, Risk/Reward, and risk percent.
- **Where to find it:** Paper Trading → Order Ticket footer.
- **How to use it:** Reduce quantity if risk is too high. Place only when risk fits your guideline.
- **Example:** Risk ₹300 on ₹10 lakh is 0.03%, which is manageable.

#### ✅ Imported Scanner Recommendation
- **What it does:** Auto-fills the ticket from a Stock Detail recommendation.
- **Where to find it:** Stock Detail → Send to paper trading.
- **How to use it:** Send the stock. Review prefilled symbol, entry, stop, and target. Place only after checking risk.
- **Example:** HINDZINC fills entry around ₹505, stop ₹470, target ₹550.

#### ✅ Paper Chart
- **What it does:** Shows candles, volume, EMA20, Supertrend, and ticket levels.
- **Where to find it:** Paper Trading → below Order Ticket.
- **How to use it:** Confirm entry, stop, and target lines sit in sensible places.
- **Example:** Stop line at ₹470 should sit below support, not randomly near current price.

#### ✅ Update SL / TP
- **What it does:** Updates stop loss and target for the selected open position.
- **Where to find it:** Paper Trading → Trade details panel.
- **How to use it:** Select a position. Enter new stop-loss or target. Click Update SL / TP.
- **Example:** HINDZINC moves from ₹500 to ₹540, so raise stop from ₹470 to ₹510.

---

# 📱 Settings and Configuration

> Settings are split across the app: Fyers access key and paper account settings are in Paper Trading → Account, while risk settings and app health are in Home → Admin.

---

## 🗂️ Section: Fyers Access Key Input

**What this section does:**
This section connects the app to Fyers market data. Without a working access key, scans and live quotes may fail.

**Real-life example:**
Think of the access key like your house key. The app can stand at the door, but it cannot enter the data room without the key.

### Features in this section:

#### ✅ Save Access Key
- **What it does:** Saves your Fyers access key for scanner and price features.
- **Where to find it:** Paper Trading → Account → FYERS Access Key → Update Access key.
- **How to use it:** Paste the access key. Click Save Access Key. Confirm Access Key Active ✅.
- **Example:** Paste a new Fyers key before scanning HINDZINC and RELIANCE.

#### ✅ Access Key Info and History
- **What it does:** Shows last saved time, last error, current status, and masked history.
- **Where to find it:** Paper Trading → Account → FYERS Access Key.
- **How to use it:** Check status before running scanner. Replace the access key if expired.
- **Example:** Last Error says access key expired, so generate a new Fyers key and save it.

---

## 🗂️ Section: Scanner Config

**What this section does:**
Scanner config controls what the app scans and how much data it studies. These settings live in the Scanner header and can be saved as presets.

**Real-life example:**
Think of this like setting the lens on a camera. The same market looks different through 1h, 4h, and 1d views.

### Features in this section:

#### ✅ Timeframe, Lookback, Top Set, and Universe
- **What it does:** Sets candle size, history length, shortlist size, and stock group.
- **Where to find it:** Scanner header.
- **How to use it:** Choose 1d, lookback 180, top 20, NIFTY500 for a normal swing scan.
- **Example:** Use 1d and lookback 180 to find HINDZINC swing trades around ₹500.

#### ✅ Saved Presets
- **What it does:** Stores scanner config for reuse.
- **Where to find it:** Scanner → Save Scan, then Home → Saved Scans.
- **How to use it:** Save a named setup and load it later.
- **Example:** Save “Daily NIFTY500 swing” for your morning routine.

---

## 🗂️ Section: Risk Settings

**What this section does:**
Risk settings control broad account risk guidance and paper-trading risk checks. They help keep losses small while you practise.

**Real-life example:**
Risk settings are like a seat belt. They do not make the car faster, but they protect you when something goes wrong.

### Features in this section:

#### ✅ Risk Profile
- **What it does:** Sets your risk style.
- **Where to find it:** Home → Admin → Risk profile.
- **How to use it:** Choose conservative, moderate, or aggressive. Save risk.
- **Example:** Conservative may suit a ₹2 lakh beginner account better than aggressive.

#### ✅ Position Size and Max Risk
- **What it does:** Sets normal trade size and maximum loss guideline per trade.
- **Where to find it:** Home → Admin → Risk profile and Paper Trading risk preview.
- **How to use it:** Enter values like 10% position size and 2% max risk. Reduce quantity when warned.
- **Example:** 2% of ₹10 lakh means do not risk more than ₹20,000 on one trade.

---

# ❓ Common Questions (FAQ)

## What does “BUY candidate” mean?
A BUY candidate passed the scanner and final recommendation checks. It does not guarantee profit. It means the setup is ready enough to review for a possible paper trade.

## What does “WATCH candidate” mean?
A WATCH candidate looks promising but needs more confirmation. Treat it like a stock on your shortlist, not a stock to buy immediately.

## Why are some stocks showing 0.0 values?
A 0.0 or N/A value usually means the app did not receive enough usable price data for that field. Check your Fyers access key, scan again, or increase lookback.

## What is a good technical score?
A score above 70 is generally worth reviewing. A score above 85 is stronger, but still check news, trade plan, and Risk/Reward.

## How often should I run the scanner?
For swing trading, run it once after market opens and once near market close. Avoid scanning every few minutes unless you are testing.

## What is paper trading and why use it?
Paper trading is practice trading with virtual money. Use it to build discipline and learn without risking real capital.

## My FYERS Access Key expired — what do I do?
Generate a new Fyers access key from the Fyers developer dashboard. Go to Paper Trading → Account → FYERS Access Key, paste it, and click Save Access Key.

## The scanner shows 755 stocks but only 247 have data — why?
This means many symbols did not return enough usable price history. Common reasons are expired access key, missing provider data, symbol format issues, or too little lookback history.

---

# 📖 Glossary (Plain English Definitions)

## Supertrend
A trend guide that turns positive or negative based on price movement. It is like a traffic signal for trend direction.

## EMA 20
A 20-period moving average that reacts faster to recent prices. It is like a short-term trend line.

## SMA
A simple moving average. It smooths price over a chosen number of candles so you can see broad direction.

## MACD
A momentum tool that compares moving averages. It helps show whether buying strength is improving or weakening.

## RSI
A strength meter for price movement. Above 50 often supports bullish trades, while very high readings can mean the stock is stretched.

## Stop Loss
The price where you exit if the trade goes wrong. It is like a safety net below a tightrope walker.

## Target
The price where you plan to take profit. Target 1 is the first goal, Target 2 is the bigger goal.

## Risk/Reward
A comparison of possible profit versus possible loss. A 2.0 Risk/Reward means possible profit is twice the possible loss.

## Win Rate
The percentage of past trades that made money. It is like a batsman’s success rate.

## Max Drawdown
The worst fall in capital during a test. It shows how painful the rough patch could have been.

## Screener Score
A score that ranks how well a stock passed scanner checks. Think of it like a credit score for stock health.

## Swing Trading
Holding a trade for several days or weeks to capture a medium-sized move.

## Lookback Period
The amount of past data the app studies. Lookback 180 means the app checks the last 180 candles.

## Candles
Price bars that show open, high, low, and close for a time period.

## Bollinger Bands
A price envelope around the stock. It helps show whether price is near the top, middle, or bottom of its recent range.

## ATR
Average True Range. It measures how much a stock usually moves and helps judge volatility.

## Paper Trading
Practice trading with virtual money. It lets you learn without risking real cash.

## Backtest
A replay of past market data to see how a strategy might have performed.

## Equity Curve
A chart showing how capital changed over time during a backtest or trading history.

## Sentiment
The mood of recent news. Positive, neutral, or negative sentiment can support or weaken a trade idea.

---

# 🔍 Screens and Features Discovered in the Codebase

## Screens Found
1. Home / Workstation
2. Scanner / Dashboard
3. Stock Detail Page
4. Paper Trading
5. Settings and Configuration areas inside Home and Paper Trading

## Tabs Found
1. Stock Detail: Overview, Technicals, Trade Plan, News, Backtest, Chart
2. Paper Trading: Positions, Open Orders, History, Analytics, Alerts, Account

## Major Features Found
1. Market overview, saved scans, scan history, scan comparison, alerts, risk settings, and app health
2. Scanner controls, scan summary cards, filters, candidate table, all analyzed table, save scan, export CSV, loading and retry states
3. Stock detail recommendation, technical checks, trade plan, news sentiment, backtest, and chart
4. Paper trading positions, orders, history, analytics, alerts, account, access key management, order ticket, paper chart, and trade details
5. Backend support for scanner analysis, symbol detail enrichment, latest scan restore, paper trading, notifications, alerts, risk settings, health, saved scans, and access key history

## Data Models Found
1. WatchedStock
2. AnalysisHistory
3. BacktestHistory
4. PaperTradingAccount
5. PaperPosition
6. PaperOrder
7. PaperTradeHistory
8. PaperNotification
9. PaperTransaction
10. PaperAlert
11. SavedScan
12. ScanHistorySnapshot
13. WorkstationAlert
14. RiskSettings
15. FyersToken
16. FyersTokenHistory




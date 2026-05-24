import asyncio
import json
import random
import time
import websockets

# Universe of 50 distinct Nifty stocks
SYMBOLS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "BHARTIARTL",
    "ITC", "HINDUNILVR", "LT", "BAJFINANCE", "AXISBANK", "KOTAKBANK", "MARUTI",
    "SUNPHARMA", "TITAN", "ULTRACEMCO", "ASIANPAINT", "NTPC", "M&M",
    "TATASTEEL", "POWERGRID", "TATAMOTORS", "BAJAJFINSV", "WIPRO", "NESTLEIND",
    "HCLTECH", "TECHM", "JSWSTEEL", "ONGC", "GRASIM", "HINDALCO", "CIPLA",
    "DRREDDY", "DIVISLAB", "BRITANNIA", "EICHERMOT", "APOLLOHOSP", "HEROMOTOCO",
    "ADANIENT", "ADANIPORTS", "COALINDIA", "TATACONSUM", "UPL", "BAJAJ-AUTO",
    "INDUSINDBK", "SBILIFE", "HDFCLIFE", "LTIM", "BPCL"
]

async def stream_ticks():
    uri = "ws://localhost:8000/ws/ticks"
    print(f"Connecting to mock backend ingestion endpoint: {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected. Initiating 60-second LIVE MARKET STRESS TEST...")
            start_time = time.time()
            ticks_sent = 0
            
            # Base price initialization
            prices = {sym: random.uniform(500, 3000) for sym in SYMBOLS}
            
            while time.time() - start_time < 60:
                batch_start = time.time()
                
                # Blast 1,000 ticks
                for _ in range(1000):
                    sym = random.choice(SYMBOLS)
                    # Simulated random walk
                    prices[sym] *= random.uniform(0.9995, 1.0005)
                    
                    payload = {
                        "type": "TICK_UPDATE",
                        "symbol": sym,
                        "price": round(prices[sym], 2)
                    }
                    await websocket.send(json.dumps(payload))
                    ticks_sent += 1
                
                # Pace exactly to 1 batch per second
                elapsed = time.time() - batch_start
                if elapsed < 1.0:
                    await asyncio.sleep(1.0 - elapsed)
                
            print(f"\n--- STRESS TEST COMPLETE ---")
            print(f"Time Elapsed: 60 seconds")
            print(f"Total Ticks Sent: {ticks_sent}")
            print(f"Throughput: {ticks_sent / 60:.2f} ticks/second")

    except ConnectionRefusedError:
        print(f"\n[FATAL] Connection refused. Is your FastAPI backend running on port 8000?")
    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(stream_ticks())
    except KeyboardInterrupt:
        print("\nStress test interrupted by user.")

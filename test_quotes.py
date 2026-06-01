import asyncio

async def test_fyers():
    from backend.app.services.fyers_service import FyersService
    fyers = FyersService()
    try:
        response = fyers._client().quotes(data={"symbols": "NSE:INFY-EQ"})
        print("API Response:", response)
    except Exception as e:
        print("API Error:", e)

if __name__ == "__main__":
    asyncio.run(test_fyers())

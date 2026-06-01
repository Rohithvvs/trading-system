import asyncio
from backend.app.services.paper_trading_service import PaperTradingService

async def debug_positions():
    service = PaperTradingService()
    try:
        positions = await service.get_positions()
        print(positions)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_positions())

import asyncio
from app.services.universe_service import UniverseService

async def main():
    print("Testing UniverseService...")
    all_active = await UniverseService.get_all_active_symbols()
    print("get_all_active_symbols:", len(all_active))

    nifty500 = await UniverseService.get_active_symbols("NIFTY500")
    print("get_active_symbols('NIFTY500'):", len(nifty500))
    
    if nifty500:
        print("First 5 in NIFTY500:", nifty500[:5])
        
    nifty_500_space = await UniverseService.get_active_symbols("NIFTY 500")
    print("get_active_symbols('NIFTY 500'):", len(nifty_500_space))

asyncio.run(main())

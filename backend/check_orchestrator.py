import asyncio
from app.db.session import AsyncSessionLocal
from app.agents.orchestrator_agent import OrchestratorAgent

async def main():
    async with AsyncSessionLocal() as db:
        agent = OrchestratorAgent(db)
        universes = await agent._prioritized_universes()
        for name, symbols in universes:
            print(f"{name}: {len(symbols)}")

asyncio.run(main())

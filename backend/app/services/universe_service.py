import logging
from sqlalchemy import select
from ..db.session import AsyncSessionLocal
from ..models.stock import StockMaster

logger = logging.getLogger("app.services.universe")

class UniverseService:
    @staticmethod
    async def get_active_symbols(universe: str) -> list[str]:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.scalars(
                    select(StockMaster.symbol)
                    .where(StockMaster.is_active == True)
                    .where(StockMaster.universe == universe)
                )
                symbols = list(result.all())
                return symbols
        except Exception as e:
            logger.error(f"Failed to fetch active symbols for universe {universe}: {e}")
            return []

    @staticmethod
    async def get_all_active_symbols() -> list[str]:
        try:
            async with AsyncSessionLocal() as db:
                result = await db.scalars(
                    select(StockMaster.symbol)
                    .where(StockMaster.is_active == True)
                )
                symbols = list(result.all())
                return symbols
        except Exception as e:
            logger.error(f"Failed to fetch all active symbols: {e}")
            return []

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text
async def test():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        await session.execute(text("CREATE TABLE t (id int)"))
        await session.execute(text("INSERT INTO t VALUES (1), (2)"))
        res = await session.scalars(text("SELECT id FROM t"))
        print(type(res))
        print(type(res.first()))
asyncio.run(test())

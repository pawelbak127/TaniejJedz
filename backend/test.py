import asyncio
from redis.asyncio import Redis
from app.jobs.db import get_async_session
from app.entity_resolution.cross_reference import CrossReferenceDiscovery
from app.config import get_settings

async def run():
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    async with get_async_session() as session:
        xref = CrossReferenceDiscovery(session, redis)
        stats = await xref.discover_all('warszawa')
        await session.commit()
        print(stats)
    await redis.aclose()

asyncio.run(run())

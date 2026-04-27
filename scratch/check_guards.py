import asyncio
from app.core.database import async_session
from app.models import Guard
from sqlalchemy import select

async def check():
    async with async_session() as session:
        result = await session.execute(
            select(Guard).where(Guard.is_online == True)
        )
        guards = result.scalars().all()
        print(f"Online guards: {len(guards)}")
        for g in guards:
            print(f"ID: {g.id}, Name: {g.full_name}, Lat: {g.current_latitude}, Lon: {g.current_longitude}, Token: {g.fcm_token[:15] if g.fcm_token else 'None'}...")

if __name__ == "__main__":
    asyncio.run(check())

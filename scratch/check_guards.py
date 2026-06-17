import asyncio
from sqlalchemy import select
from app.core.database import async_session
from app.models import Guard

async def main():
    async with async_session() as db:
        result = await db.execute(select(Guard))
        guards = result.scalars().all()
        print(f"Total guards in DB: {len(guards)}")
        for g in guards:
            print(f"Guard ID: {g.id}, Name: {g.full_name}, is_on_call: {g.is_on_call}, Lat: {g.current_latitude}, Lng: {g.current_longitude}, Last Update: {g.last_location_update}")

if __name__ == '__main__':
    asyncio.run(main())

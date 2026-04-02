import asyncio
import os
import sys
from sqlalchemy import select

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.models import Guard

async def main():
    async with SessionLocal() as db:
        try:
            result = await db.execute(select(Guard))
            guards = result.scalars().all()
            print(f"Found {len(guards)} guards:")
            for g in guards:
                 print(f"ID: {g.id}, Name: {getattr(g, 'full_name', 'No name')}, Online: {g.is_online}, On Call: {g.is_on_call}, Status: {g.status}, Lat: {g.current_latitude}, Lon: {g.current_longitude}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

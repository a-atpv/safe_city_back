import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.orm import selectinload

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.database import async_session as SessionLocal
from app.models import Guard, GuardDevice

async def main():
    async with SessionLocal() as db:
        try:
            result = await db.execute(
                select(Guard).options(selectinload(Guard.devices))
            )
            guards = result.scalars().all()
            print(f"Found {len(guards)} guards:")
            for g in guards:
                 print(f"ID: {g.id}, Name: {g.full_name}, Online: {g.is_online}")
                 print(f"  Devices: {len(g.devices)}")
                 for d in g.devices:
                     print(f"    Token: {d.device_token[:20]}..., Active: {d.is_active}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

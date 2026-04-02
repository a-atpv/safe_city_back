import asyncio
import os
import sys
from sqlalchemy import select

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.models import Guard, EmergencyCall

async def main():
    async with SessionLocal() as db:
        try:
            # Check Guards
            result = await db.execute(select(Guard))
            guards = result.scalars().all()
            print(f"Found {len(guards)} guards:")
            for g in guards:
                 print(f"ID: {g.id}, Name: {getattr(g, 'full_name', 'No name')}, Online: {g.is_online}, On Call: {g.is_on_call}, Status: {g.status}, Lat: {g.current_latitude}, Lon: {g.current_longitude}")
            
            # Check Emergency Calls
            result = await db.execute(select(EmergencyCall))
            calls = result.scalars().all()
            print(f"\nFound {len(calls)} emergency calls:")
            for c in calls:
                print(f"ID: {c.id}, Status: {c.status}, GuardID: {c.guard_id}, UserID: {c.user_id}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

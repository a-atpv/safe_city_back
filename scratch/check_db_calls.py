import asyncio
from sqlalchemy import select
from app.core.database import async_session
from app.models import EmergencyCall, User

async def main():
    async with async_session() as db:
        # Check users
        user_result = await db.execute(select(User))
        users = user_result.scalars().all()
        print(f"Total users in DB: {len(users)}")
        for u in users:
            print(f"User ID: {u.id}, Email: {u.email}, Phone: {u.phone}, Full Name: {u.full_name}")

        # Check emergency calls
        call_result = await db.execute(select(EmergencyCall))
        calls = call_result.scalars().all()
        print(f"\nTotal calls in DB: {len(calls)}")
        for c in calls:
            print(f"Call ID: {c.id}, Status: {c.status}, User ID: {c.user_id}, Address: {c.address}, Lat: {c.latitude}, Lng: {c.longitude}")

if __name__ == '__main__':
    asyncio.run(main())

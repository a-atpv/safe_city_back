import asyncio
import os
import sys
from sqlalchemy import select, update

# Add current directory to path
sys.path.append(os.getcwd())

try:
    from app.core.database import SessionLocal
    from app.models import Guard, EmergencyCall, CallStatus
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

async def check():
    async with SessionLocal() as db:
        # 1. Find a guard
        result = await db.execute(select(Guard).limit(1))
        guard = result.scalar_one_or_none()
        if not guard:
            print("No guard found in DB. Please run seed_test_data.py first.")
            return

        print(f"Testing with Guard ID: {guard.id} ({guard.full_name})")

        # 2. Find the searching call from the user's screenshot (or any searching call)
        result = await db.execute(select(EmergencyCall).where(EmergencyCall.status == CallStatus.SEARCHING).limit(1))
        call = result.scalar_one_or_none()
        
        if not call:
            print("No 'searching' call found. Creating one...")
            call = EmergencyCall(user_id=1, status=CallStatus.SEARCHING, latitude=51, longitude=71)
            db.add(call)
            await db.flush()
        
        print(f"Found/Created Call ID: {call.id} with status: {call.status}")

        # 3. Manually offer this call to the guard (simulate dispatch)
        call.guard_id = guard.id
        call.status = CallStatus.OFFER_SENT
        await db.commit()
        print(f"Call {call.id} is now OFFER_SENT to Guard {guard.id}")

        # 4. Now check if the active call endpoint would find it
        active_statuses = [
            CallStatus.OFFER_SENT,
            CallStatus.ACCEPTED,
            CallStatus.EN_ROUTE,
            CallStatus.ARRIVED,
        ]
        
        result = await db.execute(
            select(EmergencyCall)
            .where(
                EmergencyCall.guard_id == guard.id,
                EmergencyCall.status.in_(active_statuses)
            )
        )
        found_call = result.scalar_one_or_none()
        
        if found_call:
            print(f"✅ Success! Active call found for guard: ID {found_call.id}, Status {found_call.status}")
        else:
            print("❌ Failure: Active call still not found for guard.")

if __name__ == "__main__":
    asyncio.run(check())

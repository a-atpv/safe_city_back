import asyncio
import os
import sys
from sqlalchemy import select, update

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.database import async_session
from app.models import Guard, EmergencyCall, CallStatus
from app.services.emergency import EmergencyService
from app.services.guard import GuardShiftService

async def verify():
    async with async_session() as db:
        # 1. Find a guard
        result = await db.execute(select(Guard).limit(1))
        guard = result.scalar_one_or_none()
        if not guard:
            print("No guards found in DB")
            return

        print(f"Testing with guard ID: {guard.id}, Name: {guard.full_name}")
        
        # 2. Ensure they are online and "on call" but have NO active calls
        guard.is_online = True
        guard.is_on_call = True
        
        # Ensure no active calls for this guard
        active_statuses = [CallStatus.ACCEPTED, CallStatus.EN_ROUTE, CallStatus.ARRIVED]
        await db.execute(
            update(EmergencyCall)
            .where(EmergencyCall.guard_id == guard.id, EmergencyCall.status.in_(active_statuses))
            .values(status=CallStatus.COMPLETED)
        )
        await db.commit()
        await db.refresh(guard)
        
        print(f"Before fix attempt: is_online={guard.is_online}, is_on_call={guard.is_on_call}")
        
        # 3. Simulate end_shift logic (the part I added to routes/guard.py)
        if guard.is_on_call:
            has_active = await EmergencyService.has_active_calls(db, guard.id)
            if not has_active:
                print("No active calls found. Resetting is_on_call flag.")
                guard.is_on_call = False
                await db.flush()
            else:
                print("Guard REALLY has active calls. Blocking end_shift.")
        
        # 4. Final end_shift
        await GuardShiftService.end_shift(db, guard)
        await db.commit()
        await db.refresh(guard)
        
        print(f"After fix attempt: is_online={guard.is_online}, is_on_call={guard.is_on_call}")
        
        if not guard.is_online and not guard.is_on_call:
            print("SUCCESS: Guard is now offline and is_on_call is False")
        else:
            print("FAILURE: Guard status not updated correctly")

if __name__ == "__main__":
    asyncio.run(verify())

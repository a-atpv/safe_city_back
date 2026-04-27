import asyncio
import os
import sys
from sqlalchemy import select, update

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.database import async_session
from app.models import Guard, EmergencyCall, CallStatus
from app.services.emergency import EmergencyService

async def verify_service():
    async with async_session() as db:
        # 1. Find a guard
        result = await db.execute(select(Guard).limit(1))
        guard = result.scalar_one_or_none()
        if not guard:
            print("No guards found in DB")
            return

        print(f"Testing service with guard ID: {guard.id}")
        
        # 2. Create a call and assign it to the guard
        call = EmergencyCall(
            user_id=1, # Assume user 1 exists
            latitude=0.0,
            longitude=0.0,
            guard_id=guard.id,
            status=CallStatus.ACCEPTED
        )
        db.add(call)
        guard.is_on_call = True
        await db.commit()
        await db.refresh(call)
        await db.refresh(guard)
        
        print(f"Call created: status={call.status}, guard is_on_call={guard.is_on_call}")
        
        # 3. Update status to COMPLETED via service
        await EmergencyService.update_status(db, call, CallStatus.COMPLETED)
        await db.commit()
        await db.refresh(guard)
        
        print(f"After COMPLETED update: status={call.status}, guard is_on_call={guard.is_on_call}")
        
        if not guard.is_on_call:
            print("SUCCESS: is_on_call reset by service")
        else:
            print("FAILURE: is_on_call NOT reset by service")

if __name__ == "__main__":
    asyncio.run(verify_service())

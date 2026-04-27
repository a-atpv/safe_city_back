import asyncio
import os
import sys
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.database import async_session as SessionLocal
from app.models import SecurityCompany, EmergencyCall, User, CallStatus
from app.services.emergency import EmergencyService
from app.services.dispatch import DispatchService

async def test_sos_flow():
    async with SessionLocal() as db:
        # 1. Ensure we have a test user
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if not user:
            print("No user found in DB. Please run seed script first.")
            return

        # 2. Setup a test company with a large radius
        # We'll use Almaty coordinates (approx 43.2, 76.9)
        test_lat, test_lon = 43.238949, 76.889709 
        
        result = await db.execute(select(SecurityCompany).limit(1))
        company = result.scalar_one_or_none()
        if not company:
            company = SecurityCompany(
                name="Test Security",
                is_active=True,
                is_accepting_calls=True,
                service_latitude=test_lat,
                service_longitude=test_lon,
                service_radius_km=100.0,
                priority=10
            )
            db.add(company)
            await db.flush()
        else:
            company.service_latitude = test_lat
            company.service_longitude = test_lon
            company.service_radius_km = 100.0
            company.is_active = True
            company.is_accepting_calls = True
            await db.flush()

        print(f"Test Company: ID={company.id}, Name={company.name}, Radius={company.service_radius_km}")

        # 3. Create an SOS call near the company
        # Almaty center is roughly the same
        call_lat, call_lon = 43.25, 76.91
        
        class MockData:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
        
        call_data = MockData(
            latitude=call_lat,
            longitude=call_lon,
            address="Test Street 123",
            type="sos"
        )
        
        print(f"Creating SOS call at ({call_lat}, {call_lon})...")
        call = await EmergencyService.create_call(db, user.id, call_data)
        print(f"Call created: ID={call.id}, Status={call.status}")

        # 4. Start search (should assign company)
        print("Starting search and geo-matching...")
        call = await EmergencyService.start_search(db, call)
        print(f"Call status: {call.status}")
        print(f"Assigned Company ID: {call.security_company_id}")

        if call.security_company_id == company.id:
            print("SUCCESS: Company correctly assigned via geo-matching!")
        else:
            print(f"FAILURE: Expected company {company.id}, got {call.security_company_id}")

        # 5. Try to assign guard (should notify admins)
        print("Attempting to assign guard (and notify admins)...")
        # Note: This will trigger notifications in logs if successful
        guard = await DispatchService().assign_nearest_guard(db, call)
        print(f"Assigned Guard: {guard}")
        
        await db.commit()

if __name__ == "__main__":
    asyncio.run(test_sos_flow())

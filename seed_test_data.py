"""
Seed script: Create a test guard company, admin, and guard.
Run: venv/bin/python3 seed_test_data.py
"""
import asyncio
from sqlalchemy import select
from app.core.database import engine, async_session
from app.models import SecurityCompany, Guard, CompanyAdmin
import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


async def seed():
    async with async_session() as db:
        # 1. Check if test company already exists
        result = await db.execute(
            select(SecurityCompany).where(SecurityCompany.name == "Test Guard Company")
        )
        company = result.scalar_one_or_none()

        if company:
            print(f"✅ Company already exists: id={company.id}, name={company.name}")
        else:
            company = SecurityCompany(
                name="Test Guard Company",
                legal_name="Test Guard Company LLP",
                phone="+77001234567",
                email="test@guardcompany.kz",
                address="Almaty, Kazakhstan",
                city="Almaty",
                description="Test guard company for development",
                is_active=True,
                is_accepting_calls=True,
                service_latitude=43.2380,
                service_longitude=76.9454,
                service_radius_km=20.0,
            )
            db.add(company)
            await db.flush()
            print(f"✅ Created company: id={company.id}, name={company.name}")

        # 2. Check if guard already exists
        result = await db.execute(
            select(Guard).where(Guard.email == "aldiyar.dev@gmail.com")
        )
        guard = result.scalar_one_or_none()

        if guard:
            print(f"✅ Guard already exists: id={guard.id}, email={guard.email}")
        else:
            guard = Guard(
                security_company_id=company.id,
                email="aldiyar.dev@gmail.com",
                full_name="Aldiyar",
                phone="+77001234567",
                status="active",
                is_online=False,
                is_on_call=False,
            )
            db.add(guard)
            await db.flush()
            print(f"✅ Created guard: id={guard.id}, email={guard.email}")

        # 3. Check if admin already exists
        result = await db.execute(
            select(CompanyAdmin).where(CompanyAdmin.email == "admin@testguard.kz")
        )
        admin = result.scalar_one_or_none()

        if admin:
            print(f"✅ Admin already exists: id={admin.id}, email={admin.email}")
        else:
            admin = CompanyAdmin(
                security_company_id=company.id,
                email="admin@testguard.kz",
                password_hash=hash_password("admin123"),
                full_name="Test Admin",
                role="owner",
                is_active=True,
            )
            db.add(admin)
            await db.flush()
            print(f"✅ Created admin: id={admin.id}, email={admin.email}")

        await db.commit()
        print("\n🎉 Seed complete!")
        print(f"   Company: '{company.name}' (id={company.id})")
        print(f"   Guard:   '{guard.email}' (id={guard.id})")
        print(f"   Admin:   '{admin.email}' / password: admin123")


if __name__ == "__main__":
    asyncio.run(seed())

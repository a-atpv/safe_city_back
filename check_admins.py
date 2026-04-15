import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import async_session
from app.models.user import User, UserRole
from app.models.company_admin import CompanyAdmin

async def main():
    async with async_session() as session:
        result = await session.execute(select(User).where(User.role == UserRole.ADMIN))
        app_admins = result.scalars().all()
        print(f"App Admins: {len(app_admins)}")
        for admin in app_admins:
            print(f"- Email: {admin.email}, Name: {admin.full_name}, Phone: {admin.phone}")

        result2 = await session.execute(select(CompanyAdmin))
        company_admins = result2.scalars().all()
        print(f"\nCompany Admins: {len(company_admins)}")
        for admin in company_admins:
            print(f"- Email: {admin.email}, Name: {admin.full_name}, Company ID: {admin.security_company_id}, Role: {admin.role}")

if __name__ == "__main__":
    asyncio.run(main())

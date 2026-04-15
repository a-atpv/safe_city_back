import asyncio
import sys
from sqlalchemy.future import select
from app.core.database import async_session
from app.models import SecurityCompany, CompanyAdmin
from app.services.admin import CompanyAdminService

async def get_companies(session):
    result = await session.execute(select(SecurityCompany))
    return result.scalars().all()

async def list_companies():
    async with async_session() as session:
        companies = await get_companies(session)
        if not companies:
            print("No companies found in database.")
            return None
        
        print("\nAvailable Companies:")
        for idx, company in enumerate(companies, 1):
            print(f"{idx}. {company.name} (ID: {company.id})")
        return companies

async def main():
    print("=== Safe City Admin Creation Utility ===")
    
    async with async_session() as session:
        companies = await get_companies(session)
        
        if not companies:
            print("\nError: No security companies found. Please create a company first or run seed_test_data.py.")
            sys.exit(1)
            
        print("\nSelect a company for the new admin:")
        for idx, company in enumerate(companies, 1):
            print(f"{idx}. {company.name} (ID: {company.id})")
        
        try:
            choice = int(input(f"\nEnter choice (1-{len(companies)}): "))
            selected_company = companies[choice - 1]
        except (ValueError, IndexError):
            print("Invalid selection.")
            sys.exit(1)
            
        print(f"\nCreating admin for: {selected_company.name}")
        
        email = input("Admin Email: ").strip().lower()
        full_name = input("Full Name: ").strip()
        password = input("Password: ").strip()
        
        role_input = input("Role [admin/owner] (default: admin): ").strip()
        role = role_input if role_input else "admin"
            
        try:
            # Check if admin already exists
            existing = await CompanyAdminService.get_by_email(session, email)
            if existing:
                print(f"Error: Admin with email {email} already exists.")
                sys.exit(1)
                
            admin = await CompanyAdminService.create(
                session,
                security_company_id=selected_company.id,
                email=email,
                password=password,
                full_name=full_name,
                role=role
            )
            await session.commit()
            print(f"\n✅ Success! Admin created:")
            print(f"   Email: {admin.email}")
            print(f"   Name:  {admin.full_name}")
            print(f"   Role:  {admin.role}")
            print(f"   Company: {selected_company.name}")
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error creating admin: {e}")
            sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)

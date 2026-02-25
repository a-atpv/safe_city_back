from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import CompanyAdmin, SecurityCompany
from app.core.security import get_password_hash, verify_password


class CompanyAdminService:
    """Service for company admin management"""

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[CompanyAdmin]:
        """Get admin by email"""
        result = await db.execute(
            select(CompanyAdmin).where(CompanyAdmin.email == email.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, admin_id: int) -> Optional[CompanyAdmin]:
        """Get admin by ID"""
        result = await db.execute(
            select(CompanyAdmin).where(CompanyAdmin.id == admin_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_with_company(db: AsyncSession, admin_id: int) -> Optional[CompanyAdmin]:
        """Get admin with company info"""
        result = await db.execute(
            select(CompanyAdmin)
            .options(selectinload(CompanyAdmin.security_company))
            .where(CompanyAdmin.id == admin_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> Optional[CompanyAdmin]:
        """Authenticate admin with email and password"""
        admin = await CompanyAdminService.get_by_email(db, email)
        if not admin or not admin.is_active:
            return None
        if not verify_password(password, admin.password_hash):
            return None
        return admin

    @staticmethod
    async def create(
        db: AsyncSession,
        security_company_id: int,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "admin"
    ) -> CompanyAdmin:
        """Create new company admin"""
        admin = CompanyAdmin(
            security_company_id=security_company_id,
            email=email.lower(),
            password_hash=get_password_hash(password),
            full_name=full_name,
            role=role,
        )
        db.add(admin)
        await db.flush()
        await db.refresh(admin)
        return admin

    @staticmethod
    async def change_password(
        db: AsyncSession,
        admin: CompanyAdmin,
        new_password: str
    ) -> CompanyAdmin:
        """Change admin password"""
        admin.password_hash = get_password_hash(new_password)
        await db.flush()
        return admin

    @staticmethod
    async def list_by_company(
        db: AsyncSession,
        company_id: int
    ) -> list[CompanyAdmin]:
        """List all admins for a company"""
        result = await db.execute(
            select(CompanyAdmin).where(
                CompanyAdmin.security_company_id == company_id
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def delete(db: AsyncSession, admin: CompanyAdmin) -> bool:
        """Deactivate admin"""
        admin.is_active = False
        await db.flush()
        return True

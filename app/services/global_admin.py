from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import GlobalAdmin, CompanyAdmin, User, Guard
from app.core.security import get_password_hash, verify_password
from app.services.admin import CompanyAdminService
from app.services.notifications import notification_service
from app.services.user import UserService
from app.services.guard import GuardService


class GlobalAdminService:
    """Service for system-wide global admin management"""

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[GlobalAdmin]:
        """Get global admin by email"""
        result = await db.execute(
            select(GlobalAdmin).where(GlobalAdmin.email == email.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, admin_id: int) -> Optional[GlobalAdmin]:
        """Get global admin by ID"""
        result = await db.execute(
            select(GlobalAdmin).where(GlobalAdmin.id == admin_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def authenticate(db: AsyncSession, email: str, password: str) -> Optional[GlobalAdmin]:
        """Authenticate global admin with email and password"""
        admin = await GlobalAdminService.get_by_email(db, email)
        if not admin or not admin.is_active:
            return None
        if not verify_password(password, admin.password_hash):
            return None
        return admin

    @staticmethod
    async def create(
        db: AsyncSession,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "superadmin"
    ) -> GlobalAdmin:
        """Create new global admin"""
        admin = GlobalAdmin(
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
        admin: GlobalAdmin,
        new_password: str
    ) -> GlobalAdmin:
        """Change global admin password"""
        admin.password_hash = get_password_hash(new_password)
        await db.flush()
        return admin

    @staticmethod
    async def delete(db: AsyncSession, admin: GlobalAdmin) -> bool:
        """Deactivate global admin"""
        admin.is_active = False
        await db.flush()
        return True

    @staticmethod
    async def create_company_admin(
        db: AsyncSession,
        security_company_id: int,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        role: str = "admin"
    ) -> CompanyAdmin:
        """Create a company admin (privileged action for global admins)"""
        return await CompanyAdminService.create(
            db,
            security_company_id=security_company_id,
            email=email,
            password=password,
            full_name=full_name,
            role=role
        )

    @staticmethod
    async def send_global_notification(
        db: AsyncSession,
        title: str,
        body: str,
        data: Optional[dict] = None
    ) -> int:
        """Send a notification to all users and guards in the system"""
        user_tokens = await UserService.get_all_fcm_tokens(db)
        guard_tokens = await GuardService.get_all_fcm_tokens(db)
        
        all_tokens = list(set(user_tokens + guard_tokens))
        
        if not all_tokens:
            return 0
            
        await notification_service.broadcast_to_all(
            tokens=all_tokens,
            title=title,
            body=body,
            data=data
        )
        
        return len(all_tokens)

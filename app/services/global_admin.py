from typing import Optional, List, Tuple
from collections import Counter
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import GlobalAdmin, CompanyAdmin, User, Guard, SecurityCompany, EmergencyCall
from app.core.security import get_password_hash, verify_password
from app.services.admin import CompanyAdminService
from app.services.notifications import notification_service
from app.services.user import UserService
from app.services.guard import GuardService


# Colours companies are drawn with on the platform map. Deliberately excludes the
# SOS red (#E74C3C) and the "on call" yellow (#F1C40F) the map already uses for
# call and guard state — a company must never be mistaken for an alarm.
# Duplicated in migration d5b3f1a97c24 (which backfilled existing rows) on
# purpose: editing this list must not rewrite history.
COMPANY_MAP_PALETTE: Tuple[str, ...] = (
    '#4F8CFF',  # синий
    '#2ECC71',  # зелёный
    '#F5A623',  # оранжевый
    '#B57BFF',  # фиолетовый
    '#00D2D3',  # бирюзовый
    '#FF7AC8',  # розовый
    '#A3E635',  # салатовый
    '#C68B59',  # охра
)


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


class CompanyExistsError(Exception):
    """An account with this email is already taken by another company admin."""


class PlatformCompanyService:
    """Cross-company management: what the platform owner does to companies.

    Everything *inside* a company (guards, calls, analytics) stays in
    admin.py / CompanyAdminService — the global admin reaches it by borrowing a
    company session, not through a second copy of those endpoints.
    """

    # A guard row is a ГБР unit only while it is active: deactivated ones keep
    # their history but must not be counted or drawn on the map.
    ACTIVE_GUARD = Guard.status == "active"

    @staticmethod
    async def pick_map_color(db: AsyncSession) -> str:
        """Pick the least-used palette colour, so new companies stay distinguishable."""
        used = (await db.execute(
            select(SecurityCompany.map_color).where(SecurityCompany.map_color.isnot(None))
        )).scalars().all()

        usage = Counter(c.upper() for c in used if c)
        return min(COMPANY_MAP_PALETTE, key=lambda color: usage.get(color.upper(), 0))

    @staticmethod
    async def _counters(db: AsyncSession) -> Tuple[dict, dict, dict]:
        """(guards_total, guards_online, admins_total) keyed by company id."""
        guard_rows = (await db.execute(
            select(
                Guard.security_company_id,
                func.count(Guard.id),
                func.count(Guard.id).filter(Guard.is_online.is_(True)),
            )
            .where(PlatformCompanyService.ACTIVE_GUARD)
            .group_by(Guard.security_company_id)
        )).all()

        admin_rows = (await db.execute(
            select(CompanyAdmin.security_company_id, func.count(CompanyAdmin.id))
            .where(CompanyAdmin.is_active.is_(True))
            .group_by(CompanyAdmin.security_company_id)
        )).all()

        total = {cid: n for cid, n, _ in guard_rows}
        online = {cid: n for cid, _, n in guard_rows}
        admins = {cid: n for cid, n in admin_rows}
        return total, online, admins

    @staticmethod
    async def list_companies(db: AsyncSession) -> List[dict]:
        """All companies with their unit counters, newest-priority first."""
        companies = (await db.execute(
            select(SecurityCompany).order_by(
                SecurityCompany.is_active.desc(),
                SecurityCompany.priority.desc(),
                SecurityCompany.id,
            )
        )).scalars().all()

        total, online, admins = await PlatformCompanyService._counters(db)

        return [
            {
                **{c.name: getattr(company, c.name) for c in company.__table__.columns},
                "guards_total": total.get(company.id, 0),
                "guards_online": online.get(company.id, 0),
                "admins_total": admins.get(company.id, 0),
            }
            for company in companies
        ]

    @staticmethod
    async def get_company(db: AsyncSession, company_id: int) -> Optional[SecurityCompany]:
        result = await db.execute(
            select(SecurityCompany).where(SecurityCompany.id == company_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_company(
        db: AsyncSession,
        data: dict,
        owner_email: Optional[str] = None,
        owner_password: Optional[str] = None,
        owner_full_name: Optional[str] = None,
    ) -> Tuple[SecurityCompany, Optional[CompanyAdmin]]:
        """Create a company and, when credentials are given, its owner admin."""
        if owner_email:
            existing = await CompanyAdminService.get_by_email(db, owner_email)
            if existing:
                raise CompanyExistsError(f"Admin with email {owner_email} already exists")

        if not data.get("map_color"):
            data["map_color"] = await PlatformCompanyService.pick_map_color(db)

        company = SecurityCompany(**data)
        db.add(company)
        await db.flush()

        owner = None
        if owner_email and owner_password:
            owner = await CompanyAdminService.create(
                db,
                security_company_id=company.id,
                email=owner_email,
                password=owner_password,
                full_name=owner_full_name,
                role="owner",
            )

        await db.refresh(company)
        return company, owner

    @staticmethod
    async def update_company(
        db: AsyncSession,
        company: SecurityCompany,
        data: dict,
    ) -> SecurityCompany:
        for field, value in data.items():
            setattr(company, field, value)
        await db.flush()
        await db.refresh(company)
        return company

    @staticmethod
    async def company_usage(db: AsyncSession, company_id: int) -> dict:
        """Everything that references a company — deleting is only safe at all zeros.

        Counts every row, not just the active ones: a deactivated guard or admin
        still holds the foreign key, and calls are the company's history.
        """
        usage = {}
        for key, model in (
            ("guards", Guard),
            ("admins", CompanyAdmin),
            ("calls", EmergencyCall),
        ):
            usage[key] = (await db.execute(
                select(func.count()).select_from(model)
                .where(model.security_company_id == company_id)
            )).scalar_one()
        return usage

    @staticmethod
    async def delete_company(db: AsyncSession, company: SecurityCompany) -> None:
        await db.delete(company)
        await db.flush()

    @staticmethod
    async def map_overview(db: AsyncSession) -> Tuple[List[dict], List[Guard]]:
        """Companies (zone + colour) and the active ГБР units that have a position."""
        companies = await PlatformCompanyService.list_companies(db)

        guards = (await db.execute(
            select(Guard).where(
                PlatformCompanyService.ACTIVE_GUARD,
                Guard.current_latitude.isnot(None),
                Guard.current_longitude.isnot(None),
            )
        )).scalars().all()

        return companies, list(guards)

    @staticmethod
    async def pick_impersonation_admin(
        db: AsyncSession, company_id: int
    ) -> Optional[CompanyAdmin]:
        """The account a global admin borrows to open a company's panel.

        Prefers the owner: it is the only role that can see the company's admin
        list, so borrowing anything else would silently hide part of the panel.
        """
        result = await db.execute(
            select(CompanyAdmin)
            .where(
                CompanyAdmin.security_company_id == company_id,
                CompanyAdmin.is_active.is_(True),
            )
            .order_by((CompanyAdmin.role == "owner").desc(), CompanyAdmin.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import select, desc, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Guard, GuardShift, GuardSettings


class GuardService:
    """Service for guard management"""

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[Guard]:
        """Get guard by email address"""
        result = await db.execute(
            select(Guard).where(Guard.email == email.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, guard_id: int) -> Optional[Guard]:
        """Get guard by ID"""
        result = await db.execute(
            select(Guard).where(Guard.id == guard_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_with_company(db: AsyncSession, guard_id: int) -> Optional[Guard]:
        """Get guard with company info"""
        result = await db.execute(
            select(Guard)
            .options(selectinload(Guard.security_company))
            .where(Guard.id == guard_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        security_company_id: int,
        email: str,
        full_name: str,
        phone: Optional[str] = None,
        employee_id: Optional[str] = None
    ) -> Guard:
        """Create new guard (called by company admin)"""
        guard = Guard(
            security_company_id=security_company_id,
            email=email.lower(),
            phone=phone,
            full_name=full_name,
            employee_id=employee_id,
        )
        db.add(guard)
        await db.flush()

        # Create default settings
        settings = GuardSettings(guard_id=guard.id)
        db.add(settings)
        await db.flush()
        await db.refresh(guard)
        return guard

    @staticmethod
    async def update(db: AsyncSession, guard: Guard, data: dict) -> Guard:
        """Update guard profile"""
        for field, value in data.items():
            if value is not None:
                setattr(guard, field, value)
        await db.flush()
        await db.refresh(guard)
        return guard

    @staticmethod
    async def update_location(
        db: AsyncSession,
        guard: Guard,
        latitude: float,
        longitude: float
    ) -> Guard:
        """Update guard's real-time location"""
        guard.current_latitude = latitude
        guard.current_longitude = longitude
        guard.last_location_update = datetime.now(timezone.utc)
        await db.flush()
        return guard

    @staticmethod
    async def delete(db: AsyncSession, guard: Guard) -> bool:
        """Deactivate guard (soft delete)"""
        guard.status = "inactive"
        guard.is_online = False
        await db.flush()
        return True

    @staticmethod
    async def list_by_company(
        db: AsyncSession,
        company_id: int,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None
    ) -> tuple[List[Guard], int]:
        """List guards by company (for admin)"""
        query = select(Guard).where(Guard.security_company_id == company_id)

        if search:
            query = query.where(
                Guard.full_name.ilike(f"%{search}%") |
                Guard.email.ilike(f"%{search}%")
            )

        # Count
        count_query = select(sa_func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        # Fetch
        result = await db.execute(
            query.order_by(desc(Guard.created_at))
            .offset(offset)
            .limit(limit)
        )
        guards = result.scalars().all()
        return list(guards), total

    @staticmethod
    async def get_online_by_company(
        db: AsyncSession,
        company_id: int
    ) -> List[Guard]:
        """Get all online guards for a company"""
        result = await db.execute(
            select(Guard).where(
                Guard.security_company_id == company_id,
                Guard.is_online == True,
                Guard.status == "active"
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_rating(db: AsyncSession, guard: Guard) -> Guard:
        """Recalculate guard's average rating from reviews"""
        from app.models import Review
        result = await db.execute(
            select(
                sa_func.avg(Review.rating),
                sa_func.count(Review.id)
            ).where(Review.guard_id == guard.id)
        )
        row = result.one()
        avg_rating, count = row
        guard.rating = round(float(avg_rating), 2) if avg_rating else 5.0
        guard.total_reviews = count or 0
        await db.flush()
        return guard

    @staticmethod
    async def update_fcm_token(
        db: AsyncSession,
        guard: Guard,
        fcm_token: Optional[str]
    ) -> Guard:
        """Update guard's FCM token for push notifications"""
        guard.fcm_token = fcm_token
        await db.flush()
        await db.refresh(guard)
        return guard


class GuardShiftService:
    """Service for guard shift management"""

    @staticmethod
    async def start_shift(db: AsyncSession, guard: Guard) -> GuardShift:
        """Start a new shift (go online)"""
        guard.is_online = True
        shift = GuardShift(guard_id=guard.id)
        db.add(shift)
        await db.flush()
        await db.refresh(shift)
        return shift

    @staticmethod
    async def end_shift(db: AsyncSession, guard: Guard) -> Optional[GuardShift]:
        """End current shift (go offline)"""
        guard.is_online = False
        guard.is_on_call = False

        # Find active shift
        result = await db.execute(
            select(GuardShift).where(
                GuardShift.guard_id == guard.id,
                GuardShift.ended_at.is_(None)
            ).order_by(desc(GuardShift.started_at)).limit(1)
        )
        shift = result.scalar_one_or_none()

        if shift:
            now = datetime.now(timezone.utc)
            shift.ended_at = now
            if shift.started_at:
                shift.duration_minutes = int((now - shift.started_at).total_seconds() / 60)
            await db.flush()
            await db.refresh(shift)

        return shift

    @staticmethod
    async def get_current_shift(db: AsyncSession, guard_id: int) -> Optional[GuardShift]:
        """Get active shift for guard"""
        result = await db.execute(
            select(GuardShift).where(
                GuardShift.guard_id == guard_id,
                GuardShift.ended_at.is_(None)
            ).order_by(desc(GuardShift.started_at)).limit(1)
        )
        return result.scalar_one_or_none()


class GuardSettingsService:
    """Service for guard settings"""

    @staticmethod
    async def get_or_create(db: AsyncSession, guard_id: int) -> GuardSettings:
        """Get settings or create defaults"""
        result = await db.execute(
            select(GuardSettings).where(GuardSettings.guard_id == guard_id)
        )
        settings = result.scalar_one_or_none()
        if not settings:
            settings = GuardSettings(guard_id=guard_id)
            db.add(settings)
            await db.flush()
            await db.refresh(settings)
        return settings

    @staticmethod
    async def update(db: AsyncSession, settings: GuardSettings, data: dict) -> GuardSettings:
        """Update settings"""
        for field, value in data.items():
            if value is not None:
                setattr(settings, field, value)
        await db.flush()
        await db.refresh(settings)
        return settings

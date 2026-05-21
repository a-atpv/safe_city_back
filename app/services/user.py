from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import User, Subscription, SubscriptionStatus
from app.schemas import UserCreate, UserUpdate


class UserService:
    """Service for user management"""
    
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email address"""
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """Get user by ID"""
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_with_subscription(db: AsyncSession, user_id: int) -> Optional[User]:
        """Get user with subscription data"""
        result = await db.execute(
            select(User)
            .options(selectinload(User.subscription))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create(db: AsyncSession, email: str) -> User:
        """Create new user"""
        user = User(email=email.lower(), is_verified=True, is_new=True)
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user
    
    @staticmethod
    async def update(db: AsyncSession, user: User, data: UserUpdate) -> User:
        """Update user data"""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        
        # If user updates full_name or phone, they are no longer "new"
        if "full_name" in update_data or "phone" in update_data:
            user.is_new = False
            
        await db.flush()
        await db.refresh(user)
        return user
    
    @staticmethod
    async def update_location(
        db: AsyncSession, 
        user: User, 
        latitude: float, 
        longitude: float
    ) -> User:
        """Update user's last known location and broadcast to assigned guard if active call exists."""
        import logging
        from datetime import datetime, timezone
        from sqlalchemy import select, desc
        from app.models import EmergencyCall, CallStatus

        logger = logging.getLogger(__name__)

        user.last_latitude = latitude
        user.last_longitude = longitude
        user.last_location_update = datetime.now(timezone.utc)
        await db.flush()

        # ── Broadcast location to guard if there is an active call ──
        try:
            active_statuses = [
                CallStatus.ACCEPTED,
                CallStatus.EN_ROUTE,
                CallStatus.ARRIVED,
            ]
            result = await db.execute(
                select(EmergencyCall)
                .where(
                    EmergencyCall.user_id == user.id,
                    EmergencyCall.status.in_(active_statuses),
                    EmergencyCall.guard_id.isnot(None),
                )
                .order_by(desc(EmergencyCall.created_at))
                .limit(1)
            )
            active_call = result.scalar_one_or_none()

            if active_call and active_call.guard_id:
                from app.api.ws.manager import manager
                await manager.send_to_guard(active_call.guard_id, {
                    "type": "user_location_update",
                    "call_id": active_call.id,
                    "latitude": latitude,
                    "longitude": longitude,
                })
                logger.debug(
                    f"WS: Sent user location ({latitude}, {longitude}) "
                    f"to guard {active_call.guard_id} for call {active_call.id}"
                )
        except Exception as e:
            # Never fail the location update because of a WS error
            logger.warning(f"WS: Failed to broadcast user location to guard: {e}")

        return user
    
    @staticmethod
    async def has_active_subscription(db: AsyncSession, user_id: int) -> bool:
        """Check if user has active subscription"""
        result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE
            )
        )
        subscription = result.scalar_one_or_none()
        return subscription is not None
    
    @staticmethod
    async def delete(db: AsyncSession, user: User) -> bool:
        """Delete user account"""
        await db.delete(user)
        return True

    @staticmethod
    async def update_fcm_token(
        db: AsyncSession,
        user: User,
        fcm_token: Optional[str]
    ) -> User:
        """Update user's FCM token for push notifications"""
        user.fcm_token = fcm_token
        await db.flush()
        await db.refresh(user)
        return user

    @staticmethod
    async def get_all_fcm_tokens(db: AsyncSession) -> List[str]:
        """Get all unique FCM tokens for users"""
        result = await db.execute(
            select(User.fcm_token).where(User.fcm_token.isnot(None))
        )
        return [str(token) for token in result.scalars().all() if token]

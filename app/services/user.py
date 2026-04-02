from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import User, Subscription, UserDevice, SubscriptionStatus
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
        user = User(email=email.lower(), is_verified=True)
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
        """Update user's last known location"""
        from datetime import datetime, timezone
        user.last_latitude = latitude
        user.last_longitude = longitude
        user.last_location_update = datetime.now(timezone.utc)
        await db.flush()
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


class DeviceService:
    """Service for user devices management"""
    
    @staticmethod
    async def register_device(
        db: AsyncSession,
        user_id: int,
        device_token: str,
        device_type: str,
        device_model: Optional[str] = None,
        app_version: Optional[str] = None
    ) -> UserDevice:
        """Register or update user device"""
        # Check if device exists
        result = await db.execute(
            select(UserDevice).where(
                UserDevice.user_id == user_id,
                UserDevice.device_token == device_token
            )
        )
        device = result.scalar_one_or_none()
        
        if device:
            device.device_type = device_type
            device.device_model = device_model
            device.app_version = app_version
            device.is_active = True
        else:
            device = UserDevice(
                user_id=user_id,
                device_token=device_token,
                device_type=device_type,
                device_model=device_model,
                app_version=app_version
            )
            db.add(device)
        
        await db.flush()
        await db.refresh(device)
        return device

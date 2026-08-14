from datetime import datetime, timezone
from typing import Optional, Union

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


class UserRole(str, enum.Enum):
    USER = "user"
    GUARD = "guard"
    ADMIN = "admin"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"


def is_subscription_current(
    status: Union[SubscriptionStatus, str, None],
    expires_at: Optional[datetime],
    now: Optional[datetime] = None,
) -> bool:
    """Whether a subscription row actually grants access right now.

    `status == active` is not enough on its own: a lapsed row keeps that status
    until the daily job flips it, and a hand-written grant is flipped by nothing
    at all — so the stored status runs ahead of reality by up to days. Access
    ends at `expires_at`, and everything user-facing must agree on that.

    The SQL form of the same rule lives in `UserService.has_active_subscription`
    and `app.bot.stats` — keep the three in step.
    """
    if status != SubscriptionStatus.ACTIVE:
        return False
    if expires_at is None:
        return True  # open-ended grant: never lapses
    # Rows written before the column was timezone-aware read back naive; treat
    # them as UTC rather than crashing the comparison.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > (now or datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(20), nullable=True)
    full_name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    
    status = Column(Enum(UserStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]), default=UserStatus.ACTIVE)
    role = Column(Enum(UserRole, native_enum=False, values_callable=lambda x: [e.value for e in x]), default=UserRole.USER)
    is_verified = Column(Boolean, default=False)
    is_new = Column(Boolean, default=True, nullable=False)
    secret_phrase = Column(String(255), nullable=True)
    
    # Location (last known)
    last_latitude = Column(Float, nullable=True)
    last_longitude = Column(Float, nullable=True)
    current_accuracy = Column(Float, nullable=True)  # metres — accuracy of the stored fix
    # Bumped ONLY when a fix passes quality checks — routing.py keys the 300s
    # "route to live position" window on this, so a rejected fix must not touch it.
    last_location_update = Column(DateTime(timezone=True), nullable=True)
    
    # Push notifications
    fcm_token = Column(String(500), nullable=True)
    
    # Profile extras
    city = Column(String(100), nullable=True)
    language = Column(String(5), default="ru")  # ru, kk, en
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    subscription = relationship("Subscription", back_populates="user", uselist=False)
    emergency_calls = relationship("EmergencyCall", back_populates="user")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user")
    reviews = relationship("Review", back_populates="user")
    payments = relationship("Payment", back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    status = Column(Enum(SubscriptionStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]), default=SubscriptionStatus.PENDING)
    plan_type = Column(String(50), default="monthly")  # monthly, yearly
    price = Column(Integer, nullable=True)  # в тиынах (копейках)

    # Auto-renewal: True while the sub should be recharged near expiry. Cancelling
    # sets this False (and stamps cancelled_at) so renew_due_subscriptions skips it;
    # access still runs to expires_at. A fresh recurring payment sets it back True.
    auto_renew = Column(Boolean, default=False, nullable=False)

    started_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Payment info
    payment_provider = Column(String(50), nullable=True)  # bck, appstore, googleplay
    external_subscription_id = Column(String(255), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="subscription")
    payments = relationship("Payment", back_populates="subscription")

    @property
    def is_current(self) -> bool:
        """True while this subscription still grants access — see
        [is_subscription_current]."""
        return is_subscription_current(self.status, self.expires_at)



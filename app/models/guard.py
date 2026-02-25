from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Guard(Base):
    __tablename__ = "guards"

    id = Column(Integer, primary_key=True, index=True)
    security_company_id = Column(Integer, ForeignKey("security_companies.id"), nullable=False)

    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(20), nullable=True)  # Contact phone (optional)
    full_name = Column(String(255), nullable=False)
    avatar_url = Column(String(500), nullable=True)
    employee_id = Column(String(50), nullable=True)  # Internal company number

    status = Column(String(20), default="active")  # active / inactive / blocked
    is_online = Column(Boolean, default=False)
    is_on_call = Column(Boolean, default=False)

    # Real-time location
    current_latitude = Column(Float, nullable=True)
    current_longitude = Column(Float, nullable=True)
    last_location_update = Column(DateTime(timezone=True), nullable=True)

    # Aggregated stats
    rating = Column(Float, default=5.0)
    total_reviews = Column(Integer, default=0)
    total_calls = Column(Integer, default=0)
    completed_calls = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    security_company = relationship("SecurityCompany", back_populates="guards")
    emergency_calls = relationship("EmergencyCall", back_populates="guard")
    devices = relationship("GuardDevice", back_populates="guard", cascade="all, delete-orphan")
    shifts = relationship("GuardShift", back_populates="guard", cascade="all, delete-orphan")
    settings = relationship("GuardSettings", back_populates="guard", uselist=False, cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="guard")
    reports = relationship("CallReport", back_populates="guard")
    notifications = relationship("Notification", back_populates="guard")


class GuardDevice(Base):
    __tablename__ = "guard_devices"

    id = Column(Integer, primary_key=True, index=True)
    guard_id = Column(Integer, ForeignKey("guards.id"), nullable=False)

    device_token = Column(String(500), nullable=True)  # FCM token
    device_type = Column(String(20), nullable=True)  # ios, android
    device_model = Column(String(100), nullable=True)
    app_version = Column(String(20), nullable=True)

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    guard = relationship("Guard", back_populates="devices")


class GuardShift(Base):
    __tablename__ = "guard_shifts"

    id = Column(Integer, primary_key=True, index=True)
    guard_id = Column(Integer, ForeignKey("guards.id"), nullable=False)

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_minutes = Column(Integer, nullable=True)

    # Relationships
    guard = relationship("Guard", back_populates="shifts")


class GuardSettings(Base):
    __tablename__ = "guard_settings"

    id = Column(Integer, primary_key=True, index=True)
    guard_id = Column(Integer, ForeignKey("guards.id"), unique=True, nullable=False)

    notifications_enabled = Column(Boolean, default=True)
    call_sound_enabled = Column(Boolean, default=True)
    vibration_enabled = Column(Boolean, default=True)
    language = Column(String(5), default="ru")
    dark_theme_enabled = Column(Boolean, default=True)

    # Relationships
    guard = relationship("Guard", back_populates="settings")

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class CallStatus(str, enum.Enum):
    CREATED = "created"
    SEARCHING = "searching"
    OFFER_SENT = "offer_sent"
    ACCEPTED = "accepted"
    EN_ROUTE = "en_route"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    CANCELLED_BY_USER = "cancelled_by_user"
    CANCELLED_BY_SYSTEM = "cancelled_by_system"


class EmergencyCall(Base):
    __tablename__ = "emergency_calls"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    status = Column(Enum(CallStatus), default=CallStatus.CREATED)
    
    # User location at call time
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(String(500), nullable=True)
    
    # Assigned security company/guard
    security_company_id = Column(Integer, ForeignKey("security_companies.id"), nullable=True)
    guard_id = Column(Integer, nullable=True)  # Will be FK to guard app later
    
    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    en_route_at = Column(DateTime(timezone=True), nullable=True)
    arrived_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    cancellation_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)  # Total response time
    
    # Relationships
    user = relationship("User", back_populates="emergency_calls")
    security_company = relationship("SecurityCompany", back_populates="calls")
    status_history = relationship("CallStatusHistory", back_populates="call")


class CallStatusHistory(Base):
    __tablename__ = "call_status_history"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("emergency_calls.id"), nullable=False)
    
    status = Column(Enum(CallStatus), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by = Column(String(50), nullable=True)  # user, guard, system
    meta_info = Column(Text, nullable=True)  # JSON string for extra info
    
    # Relationships
    call = relationship("EmergencyCall", back_populates="status_history")

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class CallMessage(Base):
    __tablename__ = "call_messages"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("emergency_calls.id"), nullable=False)

    sender_type = Column(String(10), nullable=False)  # user / guard
    sender_id = Column(Integer, nullable=False)  # User.id or Guard.id
    message = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    call = relationship("EmergencyCall", back_populates="messages")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)

    # One of these will be set
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    guard_id = Column(Integer, ForeignKey("guards.id"), nullable=True)

    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    type = Column(String(50), nullable=False)  # call_update, subscription, system, promo
    data = Column(Text, nullable=True)  # JSON payload

    is_read = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="notifications")
    guard = relationship("Guard", back_populates="notifications")

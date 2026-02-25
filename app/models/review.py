from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("emergency_calls.id"), unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    guard_id = Column(Integer, ForeignKey("guards.id"), nullable=False)

    rating = Column(Integer, nullable=False)  # 1-5 stars
    comment = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    call = relationship("EmergencyCall", back_populates="review")
    user = relationship("User", back_populates="reviews")
    guard = relationship("Guard", back_populates="reviews")


class CallReport(Base):
    __tablename__ = "call_reports"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("emergency_calls.id"), unique=True, nullable=False)
    guard_id = Column(Integer, ForeignKey("guards.id"), nullable=False)

    report_text = Column(Text, nullable=False)
    category = Column(String(50), nullable=True)  # theft, assault, false_alarm, other

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    call = relationship("EmergencyCall", back_populates="report")
    guard = relationship("Guard", back_populates="reports")

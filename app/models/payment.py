from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True)

    amount = Column(Integer, nullable=False)  # In smallest currency unit (тиын)
    currency = Column(String(3), default="KZT")
    status = Column(String(20), default="pending")  # pending / success / failed / refunded
    payment_method = Column(String(50), nullable=True)  # card / appstore / googleplay
    provider_transaction_id = Column(String(255), nullable=True)
    description = Column(String(500), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")

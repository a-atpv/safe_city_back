from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class FAQCategory(Base):
    __tablename__ = "faq_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    target = Column(String(20), default="both")  # user / guard / both
    order = Column(Integer, default=0)

    # Relationships
    items = relationship("FAQItem", back_populates="category", cascade="all, delete-orphan")


class FAQItem(Base):
    __tablename__ = "faq_items"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("faq_categories.id"), nullable=False)

    question = Column(String(500), nullable=False)
    answer = Column(Text, nullable=False)
    target = Column(String(20), default="both")  # user / guard / both
    order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # Relationships
    category = relationship("FAQCategory", back_populates="items")

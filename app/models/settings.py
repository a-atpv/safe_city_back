from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)

    notifications_enabled = Column(Boolean, default=True)
    call_sound_enabled = Column(Boolean, default=True)
    vibration_enabled = Column(Boolean, default=True)
    language = Column(String(5), default="ru")
    dark_theme_enabled = Column(Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="settings")

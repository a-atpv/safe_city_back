from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class SecurityCompany(Base):
    __tablename__ = "security_companies"

    id = Column(Integer, primary_key=True, index=True)
    
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    
    # Contact
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(String(500), nullable=True)
    
    # Service area (center point + radius in km)
    service_latitude = Column(Float, nullable=True)
    service_longitude = Column(Float, nullable=True)
    service_radius_km = Column(Float, default=10.0)
    
    # Company details
    city = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    license_number = Column(String(100), nullable=True)
    contract_start = Column(DateTime(timezone=True), nullable=True)
    contract_end = Column(DateTime(timezone=True), nullable=True)
    
    # Settings
    is_active = Column(Boolean, default=True)
    is_accepting_calls = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher = more priority
    response_timeout_seconds = Column(Integer, default=60)  # Time to accept call
    
    # Stats
    total_calls = Column(Integer, default=0)
    completed_calls = Column(Integer, default=0)
    average_response_time = Column(Integer, nullable=True)  # in seconds
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    calls = relationship("EmergencyCall", back_populates="security_company")
    guards = relationship("Guard", back_populates="security_company")
    admins = relationship("CompanyAdmin", back_populates="security_company")

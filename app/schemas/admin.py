from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime


# ============ Admin Auth Schemas ============

class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class AdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str = "company_admin"
    company_id: int


class AdminRefreshTokenRequest(BaseModel):
    refresh_token: str


class AdminChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


# ============ Admin Profile Schemas ============

class AdminResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    security_company_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class AdminCreate(BaseModel):
    """Used by owner to invite new admin"""
    email: EmailStr
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    role: str = "admin"


# ============ Company Schemas ============

class CompanyResponse(BaseModel):
    id: int
    name: str
    legal_name: Optional[str] = None
    logo_url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    license_number: Optional[str] = None
    service_latitude: Optional[float] = None
    service_longitude: Optional[float] = None
    service_radius_km: float = 10.0
    is_active: bool
    is_accepting_calls: bool
    total_calls: int
    completed_calls: int
    average_response_time: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    logo_url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    is_accepting_calls: Optional[bool] = None
    service_latitude: Optional[float] = None
    service_longitude: Optional[float] = None
    service_radius_km: Optional[float] = None


# ============ Analytics Schemas ============

class AnalyticsOverview(BaseModel):
    total_guards: int
    online_guards: int
    total_calls: int
    active_calls: int
    completed_calls: int
    average_rating: float
    average_response_time_minutes: Optional[int] = None


class CallAnalytics(BaseModel):
    period: str  # daily / weekly / monthly
    total: int
    completed: int
    cancelled: int
    average_response_minutes: Optional[float] = None


class GuardPerformance(BaseModel):
    guard_id: int
    full_name: str
    total_calls: int
    completed_calls: int
    rating: float
    total_reviews: int

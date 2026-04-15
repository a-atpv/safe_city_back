from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime


# ============ Guard Auth Schemas ============

class GuardEmailRequest(BaseModel):
    email: EmailStr = Field(..., description="Guard email address")


class GuardVerifyOTPRequest(BaseModel):
    email: EmailStr = Field(..., description="Guard email address")
    code: str = Field(..., min_length=4, max_length=6, description="OTP code")

    @field_validator('code')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class GuardTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str = "guard"


class GuardRefreshTokenRequest(BaseModel):
    refresh_token: str


# ============ Guard Profile Schemas ============

class GuardResponse(BaseModel):
    id: int
    email: str
    phone: Optional[str] = None
    full_name: str
    avatar_url: Optional[str] = None
    employee_id: Optional[str] = None
    status: str
    is_online: bool
    is_on_call: bool
    rating: float
    total_reviews: int
    total_calls: int
    completed_calls: int
    created_at: datetime

    class Config:
        from_attributes = True


class GuardWithCompany(GuardResponse):
    company: Optional["SecurityCompanyBrief"] = None


class GuardUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class GuardBrief(BaseModel):
    """Brief guard info for user-facing responses"""
    id: int
    full_name: str
    avatar_url: Optional[str] = None
    rating: float
    total_reviews: int

    class Config:
        from_attributes = True


# ============ Guard Shift Schemas ============

class ShiftResponse(BaseModel):
    id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None

    class Config:
        from_attributes = True


class ShiftStatusResponse(BaseModel):
    is_online: bool
    current_shift: Optional[ShiftResponse] = None


# ============ Guard Settings Schemas ============

class GuardSettingsResponse(BaseModel):
    notifications_enabled: bool = True
    call_sound_enabled: bool = True
    vibration_enabled: bool = True
    language: str = "ru"
    dark_theme_enabled: bool = True

    class Config:
        from_attributes = True


class GuardSettingsUpdate(BaseModel):
    notifications_enabled: Optional[bool] = None
    call_sound_enabled: Optional[bool] = None
    vibration_enabled: Optional[bool] = None
    language: Optional[str] = None
    dark_theme_enabled: Optional[bool] = None


# ============ Guard Device Schemas ============

class GuardDeviceRegister(BaseModel):
    device_token: str
    device_type: str = Field(..., pattern="^(ios|android)$")
    device_model: Optional[str] = None
    app_version: Optional[str] = None


# ============ Admin Guard Management Schemas ============

class GuardCreate(BaseModel):
    """Used by company admin to register a guard"""
    email: EmailStr = Field(..., description="Guard email for login")
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = None
    employee_id: Optional[str] = None


class GuardAdminUpdate(BaseModel):
    """Used by company admin to update guard"""
    full_name: Optional[str] = None
    employee_id: Optional[str] = None
    status: Optional[str] = None  # active / inactive / blocked


class GuardListResponse(BaseModel):
    guards: List[GuardResponse]
    total: int


# ============ Security Company Brief (for guard profile) ============

class SecurityCompanyBrief(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None
    phone: Optional[str] = None

    class Config:
        from_attributes = True


# Update forward refs
GuardWithCompany.model_rebuild()

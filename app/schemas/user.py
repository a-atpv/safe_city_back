from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional
from datetime import datetime


# ============ Auth Schemas ============

class EmailRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address")


class VerifyOTPRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address")
    code: str = Field(..., min_length=4, max_length=6, description="OTP code")

    @field_validator('code')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str = "user"
    isNew: bool


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ============ User Schemas ============

class UserBase(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    full_name: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_new: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    phone: Optional[str] = None
    role: str = "user"
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_verified: bool
    is_new: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserWithSubscription(UserResponse):
    subscription: Optional["SubscriptionResponse"] = None


# ============ Subscription Schemas ============

class SubscriptionResponse(BaseModel):
    id: int
    status: str
    plan_type: str
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============ Location Schemas ============

class LocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, description="Location accuracy in meters")


# ============ Secret Phrase Schemas ============

class SecretPhraseRequest(BaseModel):
    secret_phrase: str = Field(..., min_length=1, max_length=255, description="Secret phrase for emergency call cancellation")


class SecretPhraseResponse(BaseModel):
    secret_phrase: Optional[str] = Field(None, description="Secret phrase for emergency call cancellation")


# Update forward refs
UserWithSubscription.model_rebuild()

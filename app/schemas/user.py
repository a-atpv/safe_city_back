from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
from typing import Optional
from datetime import datetime

from app.models.user import SubscriptionStatus, is_subscription_current
from app.schemas.fields import AvatarUrl


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
    avatar_url: AvatarUrl = None
    is_verified: bool
    is_new: bool
    secret_phrase: Optional[str] = None
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
    auto_renew: bool = False
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def _lapsed_reads_as_expired(self) -> "SubscriptionResponse":
        """Report a lapsed subscription as expired, whatever the row still says.

        The stored status lags reality: the daily job only flips Robokassa subs,
        and after a grace window at that, so a row can read `active` for days
        past `expires_at` — a hand-written grant reads that way forever. Clients
        decide what to show from this status alone, so sending `active` paints a
        green "Подписка активна" over a subscription that `require_subscription`
        will refuse with 403 — the user is told they are covered and finds out
        otherwise by pressing SOS.

        Access itself is unaffected; this only stops the API from claiming
        otherwise. See [is_subscription_current].
        """
        if not is_subscription_current(self.status, self.expires_at):
            if self.status == SubscriptionStatus.ACTIVE.value:
                self.status = SubscriptionStatus.EXPIRED.value
        return self


# ============ Location Schemas ============

class LocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, description="Location accuracy in meters")
    fix_age_ms: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Age of the GPS fix at send time, in milliseconds. Relative (not a "
            "wall-clock timestamp) so a skewed device clock cannot poison it. "
            "Lets the server age a re-sent fix instead of treating every ping as "
            "a fresh position."
        ),
    )


# ============ Secret Phrase Schemas ============

class SecretPhraseRequest(BaseModel):
    secret_phrase: str = Field(..., min_length=1, max_length=255, description="Secret phrase for emergency call cancellation")


class SecretPhraseResponse(BaseModel):
    secret_phrase: Optional[str] = Field(None, description="Secret phrase for emergency call cancellation")


# Update forward refs
UserWithSubscription.model_rebuild()

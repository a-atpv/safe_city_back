from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ============ Review Schemas ============

class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class ReviewResponse(BaseModel):
    id: int
    call_id: int
    user_id: int
    guard_id: int
    rating: int
    comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Call Report Schemas ============

class CallReportCreate(BaseModel):
    report_text: str = Field(..., min_length=1)
    category: Optional[str] = None  # theft, assault, false_alarm, other


class CallReportResponse(BaseModel):
    id: int
    call_id: int
    guard_id: int
    report_text: str
    category: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============ Call Message Schemas ============

class CallMessageCreate(BaseModel):
    message: str = Field(..., min_length=1)


class CallMessageResponse(BaseModel):
    id: int
    call_id: int
    sender_type: str
    sender_id: int
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class CallMessagesListResponse(BaseModel):
    messages: List[CallMessageResponse]
    total: int


# ============ Notification Schemas ============

class NotificationResponse(BaseModel):
    id: int
    title: str
    body: Optional[str] = None
    type: str
    data: Optional[str] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    total: int
    unread_count: int


# ============ Payment Schemas ============

class PaymentResponse(BaseModel):
    id: int
    amount: int
    currency: str
    status: str
    payment_method: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]
    total: int


# ============ User Settings Schemas ============

class UserSettingsResponse(BaseModel):
    notifications_enabled: bool = True
    call_sound_enabled: bool = True
    vibration_enabled: bool = True
    language: str = "ru"
    dark_theme_enabled: bool = True

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    notifications_enabled: Optional[bool] = None
    call_sound_enabled: Optional[bool] = None
    vibration_enabled: Optional[bool] = None
    language: Optional[str] = None
    dark_theme_enabled: Optional[bool] = None


# ============ FAQ Schemas ============

class FAQItemResponse(BaseModel):
    id: int
    question: str
    answer: str
    category_name: Optional[str] = None

    class Config:
        from_attributes = True


class FAQListResponse(BaseModel):
    items: List[FAQItemResponse]


# ============ Support Contact Schemas ============

class SupportContactsResponse(BaseModel):
    whatsapp: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

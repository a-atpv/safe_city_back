from pydantic import BaseModel, Field
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from app.models.emergency import CallStatus

if TYPE_CHECKING:
    from app.schemas.guard import GuardBrief


class EmergencyCallCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: Optional[str] = None


class UserBrief(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class EmergencyCallResponse(BaseModel):
    id: int
    status: CallStatus
    latitude: float
    longitude: float
    address: Optional[str] = None
    
    created_at: datetime
    accepted_at: Optional[datetime] = None
    en_route_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    security_company: Optional["SecurityCompanyBrief"] = None
    user: Optional[UserBrief] = None
    guard: Optional["GuardBrief"] = None
    
    class Config:
        from_attributes = True


class EmergencyCallBrief(BaseModel):
    id: int
    status: CallStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    
    user: Optional[UserBrief] = None
    guard: Optional["GuardBrief"] = None
    security_company: Optional["SecurityCompanyBrief"] = None

    class Config:
        from_attributes = True


class CallHistoryResponse(BaseModel):
    calls: List[EmergencyCallBrief]
    total: int


class CancelCallRequest(BaseModel):
    reason: Optional[str] = None


# ============ Security Company ============

class SecurityCompanyBrief(BaseModel):
    id: int
    name: str
    logo_url: Optional[str] = None
    phone: Optional[str] = None

    class Config:
        from_attributes = True


class SecurityCompanyResponse(SecurityCompanyBrief):
    average_response_time: Optional[int] = None
    
    
# ============ Call Status Update (internal) ============

class CallStatusUpdate(BaseModel):
    status: CallStatus
    meta_info: Optional[str] = None


# Update forward refs
EmergencyCallResponse.model_rebuild()
EmergencyCallBrief.model_rebuild()

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.emergency import CallStatus


class EmergencyCallCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: Optional[str] = None


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
    
    class Config:
        from_attributes = True


class EmergencyCallBrief(BaseModel):
    id: int
    status: CallStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None

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
    metadata: Optional[str] = None


# Update forward refs
EmergencyCallResponse.model_rebuild()

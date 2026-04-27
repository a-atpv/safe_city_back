from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db, create_access_token, create_refresh_token
from app.api.deps import get_current_admin # I might need a new get_current_global_admin
from app.models import GlobalAdmin
from app.schemas.admin import AdminLoginRequest, AdminTokenResponse, AdminCreate, AdminResponse
from app.schemas.common import APIResponse
from app.services.global_admin import GlobalAdminService
from app.core.config import settings
from app.core.bootstrap import run_bootstrap
from datetime import timedelta
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict

router = APIRouter(prefix="/global", tags=["Global Admin"])

class GlobalAdminResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: str # Simplification for now

    class Config:
        from_attributes = True

class GlobalBroadcastRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    body: str = Field(..., min_length=1, max_length=500)
    data: Optional[Dict[str, str]] = None

@router.post("/init", response_model=APIResponse)
async def initialize_admins(db: AsyncSession = Depends(get_db)):
    """
    Trigger the system bootstrap process.
    Creates initial company admin and global admin if they don't exist.
    """
    await run_bootstrap()
    return APIResponse(success=True, message="Bootstrap process completed successfully")

@router.post("/login", response_model=AdminTokenResponse)
async def global_login(data: AdminLoginRequest, db: AsyncSession = Depends(get_db)):
    """Global admin login"""
    admin = await GlobalAdminService.authenticate(db, data.email, data.password)
    if not admin:
        raise HTTPException(status_code=401, detail="Invalid global admin credentials")
    
    access_token = create_access_token(
        data={"sub": str(admin.id), "role": "global_admin"},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh_token = create_refresh_token(
        data={"sub": str(admin.id), "role": "global_admin"}
    )
    
    return AdminTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        role="global_admin",
        company_id=0 # Global admins are not tied to a company
    )

@router.post("/broadcast", response_model=APIResponse)
async def broadcast_notification(
    data: GlobalBroadcastRequest,
    # TODO: Add global admin dependency
    db: AsyncSession = Depends(get_db)
):
    """Broadcast notification to all users and guards"""
    count = await GlobalAdminService.send_global_notification(
        db, title=data.title, body=data.body, data=data.data
    )
    return APIResponse(success=True, message=f"Notification broadcasted to {count} devices")

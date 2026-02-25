from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db, create_access_token, create_refresh_token, decode_token
from app.api.deps import get_current_admin
from app.models import CompanyAdmin
from app.schemas.admin import (
    AdminLoginRequest,
    AdminTokenResponse,
    AdminRefreshTokenRequest,
    AdminChangePasswordRequest,
    AdminResponse,
)
from app.schemas.common import APIResponse
from app.services.admin import CompanyAdminService
from app.core.config import settings
from app.core.security import verify_password
from datetime import timedelta

router = APIRouter(prefix="/admin/auth", tags=["Admin Authentication"])


@router.post("/login", response_model=AdminTokenResponse)
async def login(
    data: AdminLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Admin login with email and password"""
    admin = await CompanyAdminService.authenticate(db, data.email, data.password)

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    access_token = create_access_token(
        data={
            "sub": str(admin.id),
            "role": "company_admin",
            "company_id": admin.security_company_id,
        },
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh_token = create_refresh_token(
        data={
            "sub": str(admin.id),
            "role": "company_admin",
            "company_id": admin.security_company_id,
        }
    )

    return AdminTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        role="company_admin",
        company_id=admin.security_company_id
    )


@router.post("/refresh", response_model=AdminTokenResponse)
async def refresh_token(
    data: AdminRefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh admin token"""
    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh" or payload.get("role") != "company_admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    admin_id = payload.get("sub")
    admin = await CompanyAdminService.get_by_id(db, int(admin_id))

    if not admin or not admin.is_active:
        raise HTTPException(status_code=401, detail="Admin not found or inactive")

    access_token = create_access_token(
        data={
            "sub": str(admin.id),
            "role": "company_admin",
            "company_id": admin.security_company_id,
        },
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    new_refresh_token = create_refresh_token(
        data={
            "sub": str(admin.id),
            "role": "company_admin",
            "company_id": admin.security_company_id,
        }
    )

    return AdminTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        role="company_admin",
        company_id=admin.security_company_id
    )


@router.post("/change-password", response_model=APIResponse)
async def change_password(
    data: AdminChangePasswordRequest,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Change admin password"""
    if not verify_password(data.current_password, current_admin.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    await CompanyAdminService.change_password(db, current_admin, data.new_password)
    return APIResponse(success=True, message="Password changed successfully")

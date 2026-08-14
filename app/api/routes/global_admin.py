import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db, create_access_token, create_refresh_token, decode_token
from app.api.deps import get_current_global_admin
from app.models import GlobalAdmin
from app.schemas.admin import (
    AdminLoginRequest,
    AdminTokenResponse,
    AdminCreate,
    AdminRefreshTokenRequest,
    AdminResponse,
)
from app.schemas.common import APIResponse
from app.schemas.global_admin import (
    GlobalCompanyResponse,
    GlobalCompanyCreate,
    GlobalCompanyCreated,
    GlobalCompanyUpdate,
    GlobalMapCompany,
    GlobalMapGuard,
    GlobalMapResponse,
)
from app.services.global_admin import (
    GlobalAdminService,
    PlatformCompanyService,
    CompanyExistsError,
    COMPANY_MAP_PALETTE,
)
from app.core.config import settings
from app.core.bootstrap import run_bootstrap
from datetime import timedelta
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

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
async def initialize_admins(
    current_admin: GlobalAdmin = Depends(get_current_global_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger the system bootstrap process.
    Creates initial company admin and global admin if they don't exist.

    Note: bootstrap also runs automatically on application startup (see app.main.lifespan),
    so the very first global admin is created there, not through this endpoint.
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

@router.post("/refresh", response_model=AdminTokenResponse)
async def global_refresh(data: AdminRefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Refresh a global admin session.

    Without this the panel dies 30 minutes after login: the access token expires
    and the refresh token issued at /global/login had nowhere to be spent.
    """
    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh" or payload.get("role") != "global_admin":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    admin_id = payload.get("sub")
    admin = await GlobalAdminService.get_by_id(db, int(admin_id)) if admin_id else None

    if not admin or not admin.is_active:
        raise HTTPException(status_code=401, detail="Global admin not found or inactive")

    token_data = {"sub": str(admin.id), "role": "global_admin"}
    return AdminTokenResponse(
        access_token=create_access_token(
            data=token_data,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        ),
        refresh_token=create_refresh_token(data=token_data),
        expires_in=settings.access_token_expire_minutes * 60,
        role="global_admin",
        company_id=0,
    )


# ============ Companies ============

@router.get("/companies", response_model=List[GlobalCompanyResponse])
async def list_companies(
    current_admin: GlobalAdmin = Depends(get_current_global_admin),
    db: AsyncSession = Depends(get_db)
):
    """All security companies with their ГБР counters and map colour"""
    return await PlatformCompanyService.list_companies(db)


@router.get("/companies/palette", response_model=List[str])
async def map_palette(
    current_admin: GlobalAdmin = Depends(get_current_global_admin)
):
    """Colours the panel offers when picking a company colour by hand"""
    return list(COMPANY_MAP_PALETTE)


@router.post("/companies", response_model=GlobalCompanyCreated, status_code=status.HTTP_201_CREATED)
async def create_company(
    data: GlobalCompanyCreate,
    current_admin: GlobalAdmin = Depends(get_current_global_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a company and, optionally, its owner admin in one call"""
    payload = data.model_dump(exclude_unset=True)
    owner_email = payload.pop("owner_email", None)
    owner_password = payload.pop("owner_password", None)
    owner_full_name = payload.pop("owner_full_name", None)

    if owner_email and not owner_password:
        raise HTTPException(status_code=400, detail="owner_password is required when owner_email is set")

    try:
        company, owner = await PlatformCompanyService.create_company(
            db,
            data=payload,
            owner_email=owner_email,
            owner_password=owner_password,
            owner_full_name=owner_full_name,
        )
    except CompanyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    logger.info(
        "Global admin %s (%s) created company %s (id=%s), owner=%s",
        current_admin.id, current_admin.email, company.name, company.id, owner_email or "—",
    )

    companies = await PlatformCompanyService.list_companies(db)
    created = next(c for c in companies if c["id"] == company.id)
    return GlobalCompanyCreated(company=created, owner=owner)


@router.patch("/companies/{company_id}", response_model=GlobalCompanyResponse)
async def update_company(
    company_id: int,
    data: GlobalCompanyUpdate,
    current_admin: GlobalAdmin = Depends(get_current_global_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a company: colour, zone, priority, activity"""
    company = await PlatformCompanyService.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    await PlatformCompanyService.update_company(db, company, data.model_dump(exclude_unset=True))

    companies = await PlatformCompanyService.list_companies(db)
    return next(c for c in companies if c["id"] == company_id)


@router.delete("/companies/{company_id}", response_model=APIResponse)
async def delete_company(
    company_id: int,
    current_admin: GlobalAdmin = Depends(get_current_global_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a company — only while nothing references it.

    A company with guards, admins or calls is never deleted: the foreign keys
    would refuse it anyway, and its calls are history that must not disappear.
    Such a company is switched off instead (is_active=false), which keeps it out
    of dispatch while its records stay intact.
    """
    company = await PlatformCompanyService.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    usage = await PlatformCompanyService.company_usage(db, company_id)
    if any(usage.values()):
        # Русский текст: этот ответ панель показывает оператору как есть.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Компанию нельзя удалить, за ней числятся: "
                f"охранников — {usage['guards']}, админов — {usage['admins']}, "
                f"вызовов — {usage['calls']}. Отключите её вместо удаления: "
                f"«Изменить» → снять «Компания активна»."
            ),
        )

    name = company.name
    await PlatformCompanyService.delete_company(db, company)

    logger.warning(
        "Global admin %s (%s) deleted company '%s' (id=%s)",
        current_admin.id, current_admin.email, name, company_id,
    )
    return APIResponse(success=True, message=f"Компания «{name}» удалена")


@router.post("/companies/{company_id}/login-as", response_model=AdminTokenResponse)
async def login_as_company(
    company_id: int,
    current_admin: GlobalAdmin = Depends(get_current_global_admin),
    db: AsyncSession = Depends(get_db)
):
    """Borrow a company session so the platform owner can use the company panel.

    Returns an ordinary company_admin token: everything under /admin keeps
    working unchanged instead of being duplicated at platform level.
    """
    company = await PlatformCompanyService.get_company(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    admin = await PlatformCompanyService.pick_impersonation_admin(db, company_id)
    if not admin:
        raise HTTPException(
            status_code=409,
            detail="Company has no active admin — create an owner for it first",
        )

    # Audit trail: impersonation is the one action here that can look like a
    # company's own admin did something, so it must be traceable in the logs.
    logger.warning(
        "IMPERSONATION: global admin %s (%s) opened company %s (id=%s) as admin %s (%s)",
        current_admin.id, current_admin.email, company.name, company.id, admin.id, admin.email,
    )

    token_data = {
        "sub": str(admin.id),
        "role": "company_admin",
        "company_id": admin.security_company_id,
        "impersonated_by": current_admin.id,
    }
    return AdminTokenResponse(
        access_token=create_access_token(
            data=token_data,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        ),
        refresh_token=create_refresh_token(data=token_data),
        expires_in=settings.access_token_expire_minutes * 60,
        role="company_admin",
        company_id=admin.security_company_id,
    )


# ============ Map ============

@router.get("/map", response_model=GlobalMapResponse)
async def map_overview(
    current_admin: GlobalAdmin = Depends(get_current_global_admin),
    db: AsyncSession = Depends(get_db)
):
    """Everything the platform map draws, in one request.

    One call rather than one per company: the panel polls this, and N+1 requests
    would grow with every company onboarded.
    """
    companies, guards = await PlatformCompanyService.map_overview(db)

    return GlobalMapResponse(
        companies=[
            GlobalMapCompany(
                id=c["id"],
                name=c["name"],
                map_color=c["map_color"],
                service_latitude=c["service_latitude"],
                service_longitude=c["service_longitude"],
                service_radius_km=c["service_radius_km"],
                is_active=c["is_active"],
                is_accepting_calls=c["is_accepting_calls"],
                guards_total=c["guards_total"],
                guards_online=c["guards_online"],
            )
            for c in companies
        ],
        guards=[
            GlobalMapGuard(
                id=g.id,
                company_id=g.security_company_id,
                full_name=g.full_name,
                phone=g.phone,
                status=g.status,
                is_online=bool(g.is_online),
                is_on_call=bool(g.is_on_call),
                latitude=g.current_latitude,
                longitude=g.current_longitude,
                accuracy=g.current_accuracy,
                last_location_update=g.last_location_update,
            )
            for g in guards
        ],
    )


@router.post("/broadcast", response_model=APIResponse)
async def broadcast_notification(
    data: GlobalBroadcastRequest,
    current_admin: GlobalAdmin = Depends(get_current_global_admin),
    db: AsyncSession = Depends(get_db)
):
    """Broadcast notification to all users and guards"""
    count = await GlobalAdminService.send_global_notification(
        db, title=data.title, body=data.body, data=data.data
    )
    return APIResponse(success=True, message=f"Notification broadcasted to {count} devices")

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db
from app.api.deps import get_current_guard
from app.models import Guard
from app.schemas.guard import (
    GuardResponse,
    GuardWithCompany,
    GuardUpdate,
    GuardSettingsResponse,
    GuardSettingsUpdate,
    GuardDeviceRegister,
    ShiftStatusResponse,
    ShiftResponse,
)
from app.schemas.common import APIResponse
from app.schemas.user import LocationUpdate
from app.services.guard import (
    GuardService,
    GuardShiftService,
    GuardSettingsService,
)
from app.services.emergency import EmergencyService
from app.services.s3 import s3_service

router = APIRouter(prefix="/guard", tags=["Guard"])


# ============ Profile ============

@router.get("/me", response_model=GuardWithCompany)
async def get_guard_profile(
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Get current guard profile with company info"""
    guard = await GuardService.get_with_company(db, current_guard.id)
    result = GuardResponse.model_validate(guard)
    return GuardWithCompany(
        **result.model_dump(),
        company=guard.security_company if guard.security_company else None
    )


@router.patch("/me", response_model=GuardResponse)
async def update_guard_profile(
    data: GuardUpdate,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Update guard profile"""
    update_data = data.model_dump(exclude_unset=True)
    guard = await GuardService.update(db, current_guard, update_data)
    return guard


@router.post("/me/avatar", response_model=GuardResponse)
async def upload_guard_avatar(
    file: UploadFile = File(...),
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Upload or replace guard avatar photo"""
    # Delete old avatar if exists
    if current_guard.avatar_url:
        await s3_service.delete_file(current_guard.avatar_url)

    # Upload new avatar
    url = await s3_service.upload_file(file, "avatars/guards")
    current_guard.avatar_url = url
    await db.flush()
    await db.refresh(current_guard)
    return current_guard


@router.delete("/me/avatar", response_model=APIResponse)
async def delete_guard_avatar(
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Delete guard avatar photo"""
    if not current_guard.avatar_url:
        raise HTTPException(status_code=404, detail="No avatar to delete")

    await s3_service.delete_file(current_guard.avatar_url)
    current_guard.avatar_url = None
    await db.flush()
    return APIResponse(success=True, message="Avatar deleted")


# ============ Settings ============

@router.get("/settings", response_model=GuardSettingsResponse)
async def get_guard_settings(
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Get guard settings"""
    settings = await GuardSettingsService.get_or_create(db, current_guard.id)
    return settings


@router.patch("/settings", response_model=GuardSettingsResponse)
async def update_guard_settings(
    data: GuardSettingsUpdate,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Update guard settings"""
    settings = await GuardSettingsService.get_or_create(db, current_guard.id)
    update_data = data.model_dump(exclude_unset=True)
    settings = await GuardSettingsService.update(db, settings, update_data)
    return settings


# ============ Shift (online/offline) ============

@router.post("/shift/start", response_model=ShiftResponse)
async def start_shift(
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Start shift (go online)"""
    if current_guard.is_online:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already online"
        )
    shift = await GuardShiftService.start_shift(db, current_guard)
    return shift


@router.post("/shift/end", response_model=APIResponse)
async def end_shift(
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """End shift (go offline)"""
    if not current_guard.is_online:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already offline"
        )
    if current_guard.is_on_call:
        # Double check if there's REALLY an active call
        has_active = await EmergencyService.has_active_calls(db, current_guard.id)
        if not has_active:
            # Self-heal: the flag was out of sync
            current_guard.is_on_call = False
            await db.flush()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot go offline while on a call"
            )
    await GuardShiftService.end_shift(db, current_guard)
    return APIResponse(success=True, message="Shift ended")


@router.get("/shift/current", response_model=ShiftStatusResponse)
async def get_shift_status(
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Get current shift status"""
    shift = await GuardShiftService.get_current_shift(db, current_guard.id)
    return ShiftStatusResponse(
        is_online=current_guard.is_online,
        current_shift=shift
    )


# ============ Location ============

@router.post("/location", response_model=APIResponse)
async def update_location(
    data: LocationUpdate,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Update guard's real-time location"""
    await GuardService.update_location(
        db, current_guard, data.latitude, data.longitude
    )
    return APIResponse(success=True, message="Location updated")


# ============ Device ============

@router.post("/device/register", response_model=APIResponse)
async def register_device(
    data: GuardDeviceRegister,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Register guard device for push notifications"""
    await GuardService.update_fcm_token(
        db, current_guard, data.device_token
    )
    return APIResponse(success=True, message="Device registered")


@router.delete("/device/{token}", response_model=APIResponse)
async def unregister_device(
    token: str,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Unregister guard device"""
    # Simply clear the token if it matches
    if current_guard.fcm_token == token:
        await GuardService.update_fcm_token(db, current_guard, None)
        return APIResponse(success=True, message="Device unregistered")
    
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Device not found"
    )

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db
from app.api.deps import get_current_active_user
from app.models import User
from app.schemas import (
    UserResponse, 
    UserWithSubscription, 
    UserUpdate, 
    LocationUpdate,
    APIResponse,
    SubscriptionResponse,
    DeviceRegister,
)
from app.services.user import UserService
from app.services.s3 import s3_service

router = APIRouter(prefix="/user", tags=["User"])


@router.get("/me", response_model=UserWithSubscription)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user profile with subscription info"""
    user = await UserService.get_with_subscription(db, current_user.id)
    return user


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user profile"""
    user = await UserService.update(db, current_user, data)
    return user


@router.post("/me/avatar", response_model=UserResponse)
async def upload_user_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload or replace user avatar photo"""
    # Delete old avatar if exists
    if current_user.avatar_url:
        await s3_service.delete_file(current_user.avatar_url)

    # Upload new avatar
    url = await s3_service.upload_file(file, "avatars/users")
    current_user.avatar_url = url
    await db.flush()
    await db.refresh(current_user)
    return current_user


@router.delete("/me/avatar", response_model=APIResponse)
async def delete_user_avatar(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete user avatar photo"""
    if not current_user.avatar_url:
        raise HTTPException(status_code=404, detail="No avatar to delete")

    await s3_service.delete_file(current_user.avatar_url)
    current_user.avatar_url = None
    await db.flush()
    return APIResponse(success=True, message="Avatar deleted")


@router.post("/location", response_model=APIResponse)
async def update_location(
    data: LocationUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user's current location"""
    await UserService.update_location(
        db, current_user, data.latitude, data.longitude
    )
    return APIResponse(success=True, message="Location updated")


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's subscription status"""
    user = await UserService.get_with_subscription(db, current_user.id)
    if not user.subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No subscription found"
        )
    return user.subscription


@router.post("/device", response_model=APIResponse)
async def register_device(
    data: DeviceRegister,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Register or update user's device for push notifications"""
    await UserService.update_fcm_token(
        db, current_user, data.device_token
    )
    return APIResponse(success=True, message="Device registered successfully")


@router.delete("/me", response_model=APIResponse)
async def delete_account(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete user account"""
    # Clean up avatar from S3 before deleting account
    if current_user.avatar_url:
        await s3_service.delete_file(current_user.avatar_url)
    await UserService.delete(db, current_user)
    return APIResponse(success=True, message="Account deleted successfully")


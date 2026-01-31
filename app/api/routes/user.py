from fastapi import APIRouter, Depends, HTTPException, status
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
    SubscriptionResponse
)
from app.services import UserService

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


@router.delete("/me", response_model=APIResponse)
async def delete_account(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete user account"""
    await UserService.delete(db, current_user)
    return APIResponse(success=True, message="Account deleted successfully")

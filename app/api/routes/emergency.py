from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db
from app.api.deps import get_current_active_user, require_subscription
from app.models import User, CallStatus
from app.schemas import (
    EmergencyCallCreate,
    EmergencyCallResponse,
    CallHistoryResponse,
    EmergencyCallBrief,
    CancelCallRequest,
    APIResponse
)
from app.services import EmergencyService

router = APIRouter(prefix="/emergency", tags=["Emergency"])


@router.post("/call", response_model=EmergencyCallResponse)
async def create_emergency_call(
    data: EmergencyCallCreate,
    current_user: User = Depends(require_subscription),
    db: AsyncSession = Depends(get_db)
):
    """Create new emergency call (SOS button)"""
    from app.services.dispatch import DispatchService

    # Check if user already has an active call
    active_call = await EmergencyService.get_active_call(db, current_user.id)
    if active_call:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active emergency call"
        )
    
    # Create call
    call = await EmergencyService.create_call(db, current_user.id, data)
    
    # Start searching for security company
    call = await EmergencyService.start_search(db, call)
    
    # Find and assign the nearest available guard
    guard = await DispatchService.assign_nearest_guard(db, call)
    # Note: if guard is None, call stays in SEARCHING status
    # and can be manually assigned by admin or retried later
    
    # Re-fetch call with updated relationships
    call = await EmergencyService.get_by_id(db, call.id)
    
    return call


@router.get("/call/active", response_model=EmergencyCallResponse)
async def get_active_call(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's current active call if exists"""
    call = await EmergencyService.get_active_call(db, current_user.id)
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active call found"
        )
    return call


@router.get("/call/{call_id}", response_model=EmergencyCallResponse)
async def get_call(
    call_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get specific call by ID"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found"
        )
    return call


@router.post("/call/{call_id}/cancel", response_model=EmergencyCallResponse)
async def cancel_call(
    call_id: int,
    data: CancelCallRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel emergency call"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found"
        )
    
    # Check if call can be cancelled
    non_cancellable = [
        CallStatus.COMPLETED,
        CallStatus.CANCELLED_BY_USER,
        CallStatus.CANCELLED_BY_SYSTEM
    ]
    if call.status in non_cancellable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Call cannot be cancelled"
        )
    
    call = await EmergencyService.cancel_call(db, call, data.reason)
    return call


@router.get("/history", response_model=CallHistoryResponse)
async def get_call_history(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's call history"""
    calls, total = await EmergencyService.get_user_history(
        db, current_user.id, limit, offset
    )
    return CallHistoryResponse(
        calls=[EmergencyCallBrief.model_validate(c) for c in calls],
        total=total
    )

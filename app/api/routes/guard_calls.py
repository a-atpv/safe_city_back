from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db
from app.api.deps import get_current_guard
from app.models import Guard, CallStatus
from app.schemas.emergency import EmergencyCallResponse, EmergencyCallBrief, CallHistoryResponse
from app.schemas.extras import CallReportCreate, CallReportResponse, CallMessageCreate, CallMessageResponse, CallMessagesListResponse
from app.schemas.common import APIResponse
from app.services.emergency import EmergencyService

router = APIRouter(prefix="/guard", tags=["Guard Calls"])


@router.get("/call/active", response_model=EmergencyCallResponse)
async def get_active_call(
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Get guard's current active call"""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models import EmergencyCall

    active_statuses = [
        CallStatus.OFFER_SENT,
        CallStatus.ACCEPTED,
        CallStatus.EN_ROUTE,
        CallStatus.ARRIVED,
    ]
    result = await db.execute(
        select(EmergencyCall)
        .options(selectinload(EmergencyCall.security_company))
        .options(selectinload(EmergencyCall.user))
        .where(
            EmergencyCall.guard_id == current_guard.id,
            EmergencyCall.status.in_(active_statuses)
        )
        .limit(1)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active call found"
        )
    return call


@router.get("/calls/available", response_model=List[EmergencyCallResponse])
async def get_available_calls(
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """List all calls currently searching for a guard"""
    if not current_guard.is_online:
        return []
    calls = await EmergencyService.get_available_calls(db)
    return calls


@router.post("/call/{call_id}/accept", response_model=EmergencyCallResponse)
async def accept_call(
    call_id: int,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Accept incoming emergency call"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    # Verify call is in acceptable state
    if call.status not in [CallStatus.SEARCHING, CallStatus.OFFER_SENT]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Call cannot be accepted in current state"
        )

    # Verify guard belongs to assigned company
    if call.security_company_id and call.security_company_id != current_guard.security_company_id:
        raise HTTPException(status_code=403, detail="Not authorized for this call")

    # Assign guard and update status
    call.guard_id = current_guard.id
    current_guard.is_on_call = True
    call = await EmergencyService.update_status(db, call, CallStatus.ACCEPTED, "guard")
    return call


@router.post("/call/{call_id}/decline", response_model=APIResponse)
async def decline_call(
    call_id: int,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Decline incoming emergency call and reassign to next nearest guard"""
    from app.services.dispatch import DispatchService

    call = await EmergencyService.get_by_id(db, call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    # Only allow decline if the call is currently offered to this guard
    if call.status not in [CallStatus.OFFER_SENT, CallStatus.SEARCHING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Call cannot be declined in current state"
        )

    # Reassign to the next nearest guard
    next_guard = await DispatchService.reassign_after_decline(
        db, call, declining_guard=current_guard
    )

    if next_guard:
        return APIResponse(
            success=True,
            message=f"Call declined. Reassigned to {next_guard.full_name}."
        )
    else:
        return APIResponse(
            success=True,
            message="Call declined. No available guards found — call cancelled."
        )


@router.post("/call/{call_id}/en-route", response_model=EmergencyCallResponse)
async def set_en_route(
    call_id: int,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Update status to en_route"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.guard_id != current_guard.id:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status != CallStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Invalid status transition")

    call = await EmergencyService.update_status(db, call, CallStatus.EN_ROUTE, "guard")
    return call


@router.post("/call/{call_id}/arrived", response_model=EmergencyCallResponse)
async def set_arrived(
    call_id: int,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Update status to arrived"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.guard_id != current_guard.id:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status != CallStatus.EN_ROUTE:
        raise HTTPException(status_code=400, detail="Invalid status transition")

    call = await EmergencyService.update_status(db, call, CallStatus.ARRIVED, "guard")
    return call


@router.post("/call/{call_id}/complete", response_model=EmergencyCallResponse)
async def complete_call(
    call_id: int,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Complete the call"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.guard_id != current_guard.id:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status != CallStatus.ARRIVED:
        raise HTTPException(status_code=400, detail="Invalid status transition")

    # Calculate response time
    if call.created_at and call.arrived_at:
        call.response_time_minutes = int((call.arrived_at - call.created_at).total_seconds() / 60)

    current_guard.is_on_call = False
    current_guard.total_calls += 1
    current_guard.completed_calls += 1

    call = await EmergencyService.update_status(db, call, CallStatus.COMPLETED, "guard")
    return call


@router.post("/call/{call_id}/report", response_model=CallReportResponse)
async def submit_report(
    call_id: int,
    data: CallReportCreate,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Submit call report after completion"""
    from app.models import CallReport

    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.guard_id != current_guard.id:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status != CallStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Call must be completed first")

    # Check if report already exists
    from sqlalchemy import select
    existing = await db.execute(
        select(CallReport).where(CallReport.call_id == call_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Report already submitted")

    report = CallReport(
        call_id=call_id,
        guard_id=current_guard.id,
        report_text=data.report_text,
        category=data.category,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report


@router.post("/call/{call_id}/message", response_model=CallMessageResponse)
async def send_message(
    call_id: int,
    data: CallMessageCreate,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Send chat message during active call"""
    from app.models import CallMessage

    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.guard_id != current_guard.id:
        raise HTTPException(status_code=404, detail="Call not found")

    active = [CallStatus.ACCEPTED, CallStatus.EN_ROUTE, CallStatus.ARRIVED]
    if call.status not in active:
        raise HTTPException(status_code=400, detail="Call is not active")

    msg = CallMessage(
        call_id=call_id,
        sender_type="guard",
        sender_id=current_guard.id,
        message=data.message,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


@router.get("/call/{call_id}/messages", response_model=CallMessagesListResponse)
async def get_messages(
    call_id: int,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Get chat messages for a call"""
    from sqlalchemy import select
    from app.models import CallMessage

    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.guard_id != current_guard.id:
        raise HTTPException(status_code=404, detail="Call not found")

    result = await db.execute(
        select(CallMessage)
        .where(CallMessage.call_id == call_id)
        .order_by(CallMessage.created_at)
    )
    messages = result.scalars().all()
    return CallMessagesListResponse(messages=list(messages), total=len(messages))


@router.get("/history", response_model=CallHistoryResponse)
async def get_guard_call_history(
    limit: int = 20,
    offset: int = 0,
    status_filter: str = None,
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db)
):
    """Get guard's call history"""
    from sqlalchemy import select, desc
    from app.models import EmergencyCall

    query = select(EmergencyCall).where(EmergencyCall.guard_id == current_guard.id)

    if status_filter:
        try:
            filter_status = CallStatus(status_filter)
            query = query.where(EmergencyCall.status == filter_status)
        except ValueError:
            pass

    # Count
    count_result = await db.execute(
        select(EmergencyCall.id).where(EmergencyCall.guard_id == current_guard.id)
    )
    total = len(count_result.all())

    result = await db.execute(
        query.order_by(desc(EmergencyCall.created_at))
        .offset(offset)
        .limit(limit)
    )
    calls = result.scalars().all()

    return CallHistoryResponse(
        calls=[EmergencyCallBrief.model_validate(c) for c in calls],
        total=total
    )

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc, func as sa_func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db
from app.api.deps import get_current_admin, require_admin_owner
from app.models import CompanyAdmin, Guard, EmergencyCall, CallStatus, Review, User
from app.schemas.guard import GuardCreate, GuardAdminUpdate, GuardResponse, GuardListResponse
from app.schemas.admin import (
    AdminResponse,
    AdminCreate,
    CompanyResponse,
    CompanyUpdate,
    AnalyticsOverview,
    NotificationSendRequest,
)
from app.schemas.common import APIResponse
from app.services.guard import GuardService
from app.services.admin import CompanyAdminService
from app.services.notifications import notification_service

router = APIRouter(prefix="/admin", tags=["Admin Panel"])


# ============ Company Profile ============

@router.get("/company", response_model=CompanyResponse)
async def get_company(
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get company profile"""
    admin = await CompanyAdminService.get_with_company(db, current_admin.id)
    return admin.security_company


@router.patch("/company", response_model=CompanyResponse)
async def update_company(
    data: CompanyUpdate,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update company profile"""
    admin = await CompanyAdminService.get_with_company(db, current_admin.id)
    company = admin.security_company
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(company, field, value)
    await db.flush()
    await db.refresh(company)
    return company


# ============ Guard Management ============

@router.get("/guards", response_model=GuardListResponse)
async def list_guards(
    limit: int = 50,
    offset: int = 0,
    search: str = None,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all guards in the company"""
    guards, total = await GuardService.list_by_company(
        db, current_admin.security_company_id, limit, offset, search
    )
    return GuardListResponse(
        guards=[GuardResponse.model_validate(g) for g in guards],
        total=total
    )


@router.post("/guards", response_model=GuardResponse)
async def create_guard(
    data: GuardCreate,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Register a new guard"""
    # Check if email already exists
    existing = await GuardService.get_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    guard = await GuardService.create(
        db,
        security_company_id=current_admin.security_company_id,
        email=data.email,
        full_name=data.full_name,
        phone=data.phone,
        employee_id=data.employee_id,
    )
    return guard


@router.get("/guards/{guard_id}", response_model=GuardResponse)
async def get_guard(
    guard_id: int,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get guard details"""
    guard = await GuardService.get_by_id(db, guard_id)
    if not guard or guard.security_company_id != current_admin.security_company_id:
        raise HTTPException(status_code=404, detail="Guard not found")
    return guard


@router.patch("/guards/{guard_id}", response_model=GuardResponse)
async def update_guard(
    guard_id: int,
    data: GuardAdminUpdate,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update guard info"""
    guard = await GuardService.get_by_id(db, guard_id)
    if not guard or guard.security_company_id != current_admin.security_company_id:
        raise HTTPException(status_code=404, detail="Guard not found")

    update_data = data.model_dump(exclude_unset=True)
    guard = await GuardService.update(db, guard, update_data)
    return guard


@router.delete("/guards/{guard_id}", response_model=APIResponse)
async def deactivate_guard(
    guard_id: int,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate a guard"""
    guard = await GuardService.get_by_id(db, guard_id)
    if not guard or guard.security_company_id != current_admin.security_company_id:
        raise HTTPException(status_code=404, detail="Guard not found")

    await GuardService.delete(db, guard)
    return APIResponse(success=True, message="Guard deactivated")


@router.get("/guards/online", response_model=GuardListResponse)
async def get_online_guards(
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get currently online guards"""
    guards = await GuardService.get_online_by_company(db, current_admin.security_company_id)
    return GuardListResponse(
        guards=[GuardResponse.model_validate(g) for g in guards],
        total=len(guards)
    )


# ============ Call Management ============

@router.get("/calls")
async def list_calls(
    limit: int = 50,
    offset: int = 0,
    status_filter: str = None,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all calls for the company"""

    query = select(EmergencyCall).where(
        EmergencyCall.security_company_id == current_admin.security_company_id
    )

    if status_filter:
        try:
            query = query.where(EmergencyCall.status == CallStatus(status_filter))
        except ValueError:
            pass

    result = await db.execute(
        query.options(
            selectinload(EmergencyCall.guard),
            selectinload(EmergencyCall.user),
            selectinload(EmergencyCall.security_company)
        )
        .order_by(desc(EmergencyCall.created_at))
        .offset(offset).limit(limit)
    )
    calls = result.scalars().all()

    # Count
    count_result = await db.execute(
        select(EmergencyCall.id).where(
            EmergencyCall.security_company_id == current_admin.security_company_id
        )
    )
    total = len(count_result.all())

    return {"calls": calls, "total": total}


@router.get("/calls/active")
async def get_active_calls(
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get currently active calls"""

    active_statuses = [
        CallStatus.CREATED, CallStatus.SEARCHING, CallStatus.OFFER_SENT,
        CallStatus.ACCEPTED, CallStatus.EN_ROUTE, CallStatus.ARRIVED
    ]
    result = await db.execute(
        select(EmergencyCall)
        .options(
            selectinload(EmergencyCall.guard),
            selectinload(EmergencyCall.user),
            selectinload(EmergencyCall.security_company)
        )
        .where(
            EmergencyCall.security_company_id == current_admin.security_company_id,
            EmergencyCall.status.in_(active_statuses)
        )
    )
    calls = result.scalars().all()
    return {"calls": calls, "total": len(calls)}


# ============ Analytics ============

@router.get("/analytics/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard analytics overview"""

    company_id = current_admin.security_company_id

    # Guard stats
    guard_result = await db.execute(
        select(
            sa_func.count(Guard.id),
            sa_func.count(Guard.id).filter(Guard.is_online == True)
        ).where(Guard.security_company_id == company_id, Guard.status == "active")
    )
    total_guards, online_guards = guard_result.one()

    # Call stats
    call_result = await db.execute(
        select(
            sa_func.count(EmergencyCall.id),
            sa_func.count(EmergencyCall.id).filter(EmergencyCall.status == CallStatus.COMPLETED),
        ).where(EmergencyCall.security_company_id == company_id)
    )
    total_calls, completed_calls = call_result.one()

    # Active calls
    active_statuses = [
        CallStatus.CREATED, CallStatus.SEARCHING, CallStatus.OFFER_SENT,
        CallStatus.ACCEPTED, CallStatus.EN_ROUTE, CallStatus.ARRIVED
    ]
    active_result = await db.execute(
        select(sa_func.count(EmergencyCall.id)).where(
            EmergencyCall.security_company_id == company_id,
            EmergencyCall.status.in_(active_statuses)
        )
    )
    active_calls = active_result.scalar()

    # Average rating
    rating_result = await db.execute(
        select(sa_func.avg(Guard.rating)).where(
            Guard.security_company_id == company_id,
            Guard.status == "active"
        )
    )
    avg_rating = rating_result.scalar() or 5.0

    # Average response time
    resp_result = await db.execute(
        select(sa_func.avg(EmergencyCall.response_time_minutes)).where(
            EmergencyCall.security_company_id == company_id,
            EmergencyCall.response_time_minutes.isnot(None)
        )
    )
    avg_response = resp_result.scalar()

    return AnalyticsOverview(
        total_guards=total_guards or 0,
        online_guards=online_guards or 0,
        total_calls=total_calls or 0,
        active_calls=active_calls or 0,
        completed_calls=completed_calls or 0,
        average_rating=round(float(avg_rating), 2),
        average_response_time_minutes=int(avg_response) if avg_response else None,
    )


# ============ Admin Management (owner only) ============

@router.get("/admins")
async def list_admins(
    current_admin: CompanyAdmin = Depends(require_admin_owner),
    db: AsyncSession = Depends(get_db)
):
    """List all admins for the company (owner only)"""
    admins = await CompanyAdminService.list_by_company(db, current_admin.security_company_id)
    return {"admins": [AdminResponse.model_validate(a) for a in admins]}


@router.post("/admins", response_model=AdminResponse)
async def create_admin(
    data: AdminCreate,
    current_admin: CompanyAdmin = Depends(require_admin_owner),
    db: AsyncSession = Depends(get_db)
):
    """Invite new admin (owner only)"""
    existing = await CompanyAdminService.get_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    admin = await CompanyAdminService.create(
        db,
        security_company_id=current_admin.security_company_id,
        email=data.email,
        password=data.password,
        full_name=data.full_name,
        role=data.role,
    )
    return admin


@router.delete("/admins/{admin_id}", response_model=APIResponse)
async def remove_admin(
    admin_id: int,
    current_admin: CompanyAdmin = Depends(require_admin_owner),
    db: AsyncSession = Depends(get_db)
):
    """Remove admin (owner only)"""
    admin = await CompanyAdminService.get_by_id(db, admin_id)
    if not admin or admin.security_company_id != current_admin.security_company_id:
        raise HTTPException(status_code=404, detail="Admin not found")
    if admin.id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    await CompanyAdminService.delete(db, admin)
    return APIResponse(success=True, message="Admin removed")


# ============ Notification Management ============

@router.post("/notifications/send", response_model=APIResponse)
async def send_admin_notification(
    data: NotificationSendRequest,
    current_admin: CompanyAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Send a custom notification to a user or guard"""

    recipient = None
    if data.recipient_type == "user":
        result = await db.execute(select(User).where(User.id == data.recipient_id))
        recipient = result.scalar_one_or_none()
    elif data.recipient_type == "guard":
        result = await db.execute(select(Guard).where(Guard.id == data.recipient_id))
        recipient = result.scalar_one_or_none()
        # Ensure guard belongs to the same company
        if recipient and recipient.security_company_id != current_admin.security_company_id:
            raise HTTPException(status_code=403, detail="Not authorized to send notifications to this guard")
    
    if not recipient:
        raise HTTPException(
            status_code=404, 
            detail=f"{data.recipient_type.capitalize()} with ID {data.recipient_id} not found"
        )
    
    if not recipient.fcm_token:
        raise HTTPException(
            status_code=400, 
            detail=f"Target {data.recipient_type} does not have a registered device token"
        )
    
    await notification_service.send_notification(
        recipient=recipient,
        title=data.title,
        body=data.body,
        data=data.data
    )
    
    return APIResponse(success=True, message="Notification sent successfully")


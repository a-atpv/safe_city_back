from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db
from app.api.deps import get_current_active_user
from app.models import (
    User, EmergencyCall, CallStatus, Review, CallMessage,
    Notification, Payment, FAQItem, FAQCategory,
)
from app.models.settings import UserSettings
from app.schemas.extras import (
    ReviewCreate,
    ReviewResponse,
    CallMessageCreate,
    CallMessageResponse,
    CallMessagesListResponse,
    NotificationResponse,
    NotificationListResponse,
    PaymentResponse,
    PaymentListResponse,
    UserSettingsResponse,
    UserSettingsUpdate,
    FAQItemResponse,
    FAQListResponse,
    SupportContactsResponse,
)
from app.schemas.common import APIResponse
from app.services.emergency import EmergencyService
from app.services.guard import GuardService

router = APIRouter(tags=["User Extras"])


# ============ Reviews ============

@router.post("/emergency/call/{call_id}/review", response_model=ReviewResponse, tags=["Emergency"])
async def submit_review(
    call_id: int,
    data: ReviewCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Submit a review for a completed call"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.status != CallStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Call must be completed")

    if not call.guard_id:
        raise HTTPException(status_code=400, detail="No guard assigned to this call")

    # Check existing review
    existing = await db.execute(
        select(Review).where(Review.call_id == call_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Review already submitted")

    review = Review(
        call_id=call_id,
        user_id=current_user.id,
        guard_id=call.guard_id,
        rating=data.rating,
        comment=data.comment,
    )
    db.add(review)
    await db.flush()
    await db.refresh(review)

    # Update guard rating
    guard = await GuardService.get_by_id(db, call.guard_id)
    if guard:
        await GuardService.update_rating(db, guard)

    return review


# ============ Call Messages (user side) ============

@router.post("/emergency/call/{call_id}/message", response_model=CallMessageResponse, tags=["Emergency"])
async def send_message(
    call_id: int,
    data: CallMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Send chat message during active call"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Call not found")

    active = [CallStatus.ACCEPTED, CallStatus.EN_ROUTE, CallStatus.ARRIVED]
    if call.status not in active:
        raise HTTPException(status_code=400, detail="Call is not active")

    msg = CallMessage(
        call_id=call_id,
        sender_type="user",
        sender_id=current_user.id,
        message=data.message,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


@router.get("/emergency/call/{call_id}/messages", response_model=CallMessagesListResponse, tags=["Emergency"])
async def get_messages(
    call_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get chat messages for a call"""
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Call not found")

    result = await db.execute(
        select(CallMessage)
        .where(CallMessage.call_id == call_id)
        .order_by(CallMessage.created_at)
    )
    messages = result.scalars().all()
    return CallMessagesListResponse(messages=list(messages), total=len(messages))


# ============ Notifications ============

@router.get("/notifications", response_model=NotificationListResponse, tags=["Notifications"])
async def get_notifications(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user notifications"""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .offset(offset).limit(limit)
    )
    notifications = result.scalars().all()

    # Unread count
    from sqlalchemy import func as sa_func
    unread_result = await db.execute(
        select(sa_func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False
        )
    )
    unread_count = unread_result.scalar() or 0

    # Total
    total_result = await db.execute(
        select(sa_func.count(Notification.id)).where(
            Notification.user_id == current_user.id
        )
    )
    total = total_result.scalar() or 0

    return NotificationListResponse(
        notifications=[NotificationResponse.model_validate(n) for n in notifications],
        total=total,
        unread_count=unread_count,
    )


@router.patch("/notifications/{notification_id}/read", response_model=APIResponse, tags=["Notifications"])
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark notification as read"""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await db.flush()
    return APIResponse(success=True, message="Marked as read")


@router.post("/notifications/read-all", response_model=APIResponse, tags=["Notifications"])
async def mark_all_read(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read"""
    from sqlalchemy import update
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.flush()
    return APIResponse(success=True, message="All marked as read")


# ============ Payments ============

@router.get("/payments/history", response_model=PaymentListResponse, tags=["Payments"])
async def get_payment_history(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payment history"""
    result = await db.execute(
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .order_by(desc(Payment.created_at))
        .offset(offset).limit(limit)
    )
    payments = result.scalars().all()

    from sqlalchemy import func as sa_func
    total_result = await db.execute(
        select(sa_func.count(Payment.id)).where(Payment.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    return PaymentListResponse(
        payments=[PaymentResponse.model_validate(p) for p in payments],
        total=total,
    )


# ============ User Settings ============

@router.get("/user/settings", response_model=UserSettingsResponse, tags=["User"])
async def get_user_settings(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user settings"""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        await db.flush()
        await db.refresh(settings)
    return settings


@router.patch("/user/settings", response_model=UserSettingsResponse, tags=["User"])
async def update_user_settings(
    data: UserSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user settings"""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == current_user.id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        await db.flush()

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)
    await db.flush()
    await db.refresh(settings)
    return settings


# ============ FAQ / Support ============

@router.get("/support/faq", response_model=FAQListResponse, tags=["Support"])
async def get_faq(
    target: str = "user",
    db: AsyncSession = Depends(get_db)
):
    """Get FAQ items"""
    result = await db.execute(
        select(FAQItem)
        .join(FAQCategory)
        .where(
            FAQItem.is_active == True,
            FAQItem.target.in_([target, "both"])
        )
        .order_by(FAQCategory.order, FAQItem.order)
    )
    items = result.scalars().all()

    # Get category names
    faq_responses = []
    for item in items:
        resp = FAQItemResponse(
            id=item.id,
            question=item.question,
            answer=item.answer,
            category_name=None,
        )
        faq_responses.append(resp)

    return FAQListResponse(items=faq_responses)


@router.get("/support/contacts", response_model=SupportContactsResponse, tags=["Support"])
async def get_support_contacts():
    """Get support contact info"""
    return SupportContactsResponse(
        whatsapp="+77001234567",
        phone="+77001234567",
        email="support@safecity.kz",
    )

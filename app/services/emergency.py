from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import EmergencyCall, CallStatusHistory, CallStatus, SecurityCompany, User, Guard
from app.schemas import EmergencyCallCreate
from app.services.notifications import notification_service


class EmergencyService:
    """Service for emergency calls management"""
    
    @staticmethod
    async def create_call(
        db: AsyncSession,
        user_id: int,
        data: EmergencyCallCreate
    ) -> EmergencyCall:
        """Create new emergency call"""
        call = EmergencyCall(
            user_id=user_id,
            latitude=data.latitude,
            longitude=data.longitude,
            address=data.address,
            status=CallStatus.CREATED
        )
        db.add(call)
        await db.flush()
        
        # Add status history
        history = CallStatusHistory(
            call_id=call.id,
            status=CallStatus.CREATED,
            changed_by="user"
        )
        db.add(history)
        await db.flush()
        
        return await EmergencyService.get_by_id(db, call.id)
    
    @staticmethod
    async def get_by_id(db: AsyncSession, call_id: int) -> Optional[EmergencyCall]:
        """Get call by ID"""
        result = await db.execute(
            select(EmergencyCall)
            .options(
                selectinload(EmergencyCall.security_company),
                selectinload(EmergencyCall.user),
                selectinload(EmergencyCall.guard)
            )
            .where(EmergencyCall.id == call_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_active_call(db: AsyncSession, user_id: int) -> Optional[EmergencyCall]:
        """Get user's active call if exists"""
        active_statuses = [
            CallStatus.CREATED,
            CallStatus.SEARCHING,
            CallStatus.OFFER_SENT,
            CallStatus.ACCEPTED,
            CallStatus.EN_ROUTE,
            CallStatus.ARRIVED,
        ]
        result = await db.execute(
            select(EmergencyCall)
            .options(
                selectinload(EmergencyCall.security_company),
                selectinload(EmergencyCall.user),
                selectinload(EmergencyCall.guard)
            )
            .where(
                EmergencyCall.user_id == user_id,
                EmergencyCall.status.in_(active_statuses)
            )
            .order_by(desc(EmergencyCall.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_history(
        db: AsyncSession,
        user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[List[EmergencyCall], int]:
        """Get user's call history"""
        # Get total count
        count_result = await db.execute(
            select(EmergencyCall.id).where(EmergencyCall.user_id == user_id)
        )
        total = len(count_result.all())
        
        # Get calls
        result = await db.execute(
            select(EmergencyCall)
            .options(selectinload(EmergencyCall.user))
            .where(EmergencyCall.user_id == user_id)
            .order_by(desc(EmergencyCall.created_at))
            .offset(offset)
            .limit(limit)
        )
        calls = result.scalars().all()
        
        return list(calls), total
    
    @staticmethod
    async def update_status(
        db: AsyncSession,
        call: EmergencyCall,
        new_status: CallStatus,
        changed_by: str = "system",
        meta_info: Optional[str] = None
    ) -> EmergencyCall:
        """Update call status"""
        call.status = new_status
        now = datetime.now(timezone.utc)
        
        # Update timestamps based on status
        if new_status == CallStatus.ACCEPTED:
            call.accepted_at = now
        elif new_status == CallStatus.EN_ROUTE:
            call.en_route_at = now
        elif new_status == CallStatus.ARRIVED:
            call.arrived_at = now
        elif new_status in [CallStatus.COMPLETED, CallStatus.CANCELLED_BY_USER, CallStatus.CANCELLED_BY_SYSTEM]:
            if new_status == CallStatus.COMPLETED:
                call.completed_at = now
                if call.created_at:
                    call.duration_seconds = int((now - call.created_at).total_seconds())
            else:
                call.cancelled_at = now
            
            # If a guard was assigned, free them
            if call.guard_id:
                # Use scalar_one_or_none to find the guard and update status
                # We do this directly to ensure it works even if relationship isn't loaded
                result = await db.execute(select(Guard).where(Guard.id == call.guard_id))
                guard = result.scalar_one_or_none()
                if guard:
                    guard.is_on_call = False
        
        # Add to history
        history = CallStatusHistory(
            call_id=call.id,
            status=new_status,
            changed_by=changed_by,
            meta_info=meta_info
        )
        db.add(history)
        await db.flush()

        # Notify user via WebSockets
        updated_call = await EmergencyService.get_by_id(db, call.id)
        if updated_call:
            await notification_service.notify_call_status_update(updated_call)
        
        return updated_call
    
    @staticmethod
    async def cancel_call(
        db: AsyncSession,
        call: EmergencyCall,
        reason: Optional[str] = None
    ) -> EmergencyCall:
        """Cancel call by user"""
        call.cancellation_reason = reason
        return await EmergencyService.update_status(
            db, call, CallStatus.CANCELLED_BY_USER, "user"
        )
    
    @staticmethod
    async def start_search(db: AsyncSession, call: EmergencyCall) -> EmergencyCall:
        """Start searching for security company"""
        return await EmergencyService.update_status(
            db, call, CallStatus.SEARCHING, "system"
        )


    @staticmethod
    async def get_available_calls(db: AsyncSession, limit: int = 20) -> List[EmergencyCall]:
        """Get all calls currently searching for a guard (SEARCHING or OFFER_SENT)"""
        result = await db.execute(
            select(EmergencyCall)
            .options(selectinload(EmergencyCall.user))
            .where(EmergencyCall.status.in_([CallStatus.SEARCHING, CallStatus.OFFER_SENT]))
            .order_by(desc(EmergencyCall.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def has_active_calls(db: AsyncSession, guard_id: int) -> bool:
        """Check if guard has any active calls (ACCEPTED, EN_ROUTE, ARRIVED)"""
        from sqlalchemy import func as sa_func
        active_statuses = [
            CallStatus.ACCEPTED,
            CallStatus.EN_ROUTE,
            CallStatus.ARRIVED,
        ]
        result = await db.execute(
            select(sa_func.count(EmergencyCall.id)).where(
                EmergencyCall.guard_id == guard_id,
                EmergencyCall.status.in_(active_statuses)
            )
        )
        count = result.scalar()
        return count > 0


class SecurityCompanyService:
    """Service for security companies management"""
    
    @staticmethod
    async def find_available_companies(
        db: AsyncSession,
        latitude: float,
        longitude: float,
        limit: int = 5
    ) -> List[SecurityCompany]:
        """Find available security companies near location"""
        # For MVP, just get active companies ordered by priority
        # TODO: Add proper geo filtering
        result = await db.execute(
            select(SecurityCompany)
            .where(
                SecurityCompany.is_active == True,
                SecurityCompany.is_accepting_calls == True
            )
            .order_by(desc(SecurityCompany.priority))
            .limit(limit)
        )
        return list(result.scalars().all())

"""
Dispatch engine for emergency call assignment and reassignment.

Handles:
  - Finding the nearest available guard for a call
  - Reassigning a call when a guard declines
  - Creating in-app notifications for guard call offers
  - Tracking which guards already declined a call
"""

import json
from typing import Optional, List
from math import radians, cos, sin, asin, sqrt
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (
    Notification,
    EmergencyCall,
    CallStatus,
    CallStatusHistory,
    Guard,
)
from sqlalchemy.orm import selectinload
from app.services.notifications import notification_service


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points on earth (km)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(min(1.0, sqrt(a)))


class DispatchService:
    """
    Dispatch engine: finds and assigns the nearest available guard.

    Flow:
        1. User presses SOS → EmergencyCall created, status = SEARCHING
        2. DispatchService.assign_nearest_guard() finds closest online guard
           from the assigned company (or any company if none assigned)
        3. Call status → OFFER_SENT, guard gets a Notification
        4. If guard declines → DispatchService.reassign_after_decline()
           which excludes the declining guard and repeats step 2
        5. If no guards available → call status → CANCELLED_BY_SYSTEM
    """

    # Maximum distance in km to consider a guard "nearby"
    MAX_SEARCH_RADIUS_KM = 50.0

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    @classmethod
    async def assign_nearest_guard(
        cls,
        db: AsyncSession,
        call: EmergencyCall,
        exclude_guard_ids: Optional[List[int]] = None,
    ) -> Optional[Guard]:
        """
        Find the nearest available guard and assign them to the call.

        Args:
            db: Database session
            call: The emergency call to assign
            exclude_guard_ids: Guard IDs to skip (e.g. guards who already declined)

        Returns:
            The assigned Guard, or None if nobody was available
        """
        exclude_ids = exclude_guard_ids or []

        # Find candidate guards
        candidates = await cls._find_available_guards(
            db,
            call=call,
            exclude_ids=exclude_ids,
        )

        if not candidates:
            return None

        # Sort by distance to the call location
        candidates_with_dist = []
        for guard in candidates:
            if guard.current_latitude is not None and guard.current_longitude is not None:
                dist = _haversine_km(
                    call.latitude, call.longitude,
                    guard.current_latitude, guard.current_longitude,
                )
                if dist <= cls.MAX_SEARCH_RADIUS_KM:
                    candidates_with_dist.append((guard, dist))

        if not candidates_with_dist:
            return None

        # Pick the closest guard
        candidates_with_dist.sort(key=lambda x: x[1])
        chosen_guard, distance_km = candidates_with_dist[0]

        # Assign guard to the call
        call.guard_id = chosen_guard.id

        # If the call didn't have a company yet, assign the guard's company
        if not call.security_company_id:
            call.security_company_id = chosen_guard.security_company_id

        # Estimate ETA based on straight-line distance (40 km/h city speed)
        eta_minutes = max(1, int((distance_km / 40) * 60 + 0.5))
        call.estimated_arrival_minutes = eta_minutes

        # Update call status to OFFER_SENT
        call.status = CallStatus.OFFER_SENT
        history = CallStatusHistory(
            call_id=call.id,
            status=CallStatus.OFFER_SENT,
            changed_by="system",
            meta_info=json.dumps({
                "guard_id": chosen_guard.id,
                "guard_name": chosen_guard.full_name,
                "distance_km": round(distance_km, 2),
                "eta_minutes": eta_minutes,
            }),
        )
        db.add(history)

        # Create in-app notification for the guard
        notification = Notification(
            guard_id=chosen_guard.id,
            title="Новый вызов!",
            body=f"Экстренный вызов в {call.address or 'вашем районе'}. "
                 f"Расстояние: {distance_km:.1f} км, ETA: ~{eta_minutes} мин.",
            type="call_offer",
            data=json.dumps({
                "call_id": call.id,
                "latitude": call.latitude,
                "longitude": call.longitude,
                "address": call.address,
                "distance_km": round(distance_km, 2),
                "eta_minutes": eta_minutes,
            }),
        )
        db.add(notification)

        await db.flush()
        await db.refresh(call)

        # Notify the guard via WebSockets and FCM
        await notification_service.notify_new_call_offer(chosen_guard, call, distance_km)

        return chosen_guard

    @classmethod
    async def reassign_after_decline(
        cls,
        db: AsyncSession,
        call: EmergencyCall,
        declining_guard: Guard,
    ) -> Optional[Guard]:
        """
        Handle a guard declining a call: unassign them and find the next one.

        Args:
            db: Database session
            call: The emergency call that was declined
            declining_guard: The guard who declined

        Returns:
            The newly assigned Guard, or None if no more guards available
        """
        # Record the decline in status history
        history = CallStatusHistory(
            call_id=call.id,
            status=CallStatus.SEARCHING,
            changed_by="guard",
            meta_info=json.dumps({
                "action": "declined",
                "guard_id": declining_guard.id,
                "guard_name": declining_guard.full_name,
            }),
        )
        db.add(history)

        # Clear the current guard assignment
        call.guard_id = None
        call.status = CallStatus.SEARCHING

        # Collect ALL guards who have already declined this call
        declined_ids = await cls._get_declined_guard_ids(db, call.id)
        # Also include the current decliner (in case history hasn't flushed yet)
        declined_ids.add(declining_guard.id)

        await db.flush()

        # Try to find the next nearest guard
        next_guard = await cls.assign_nearest_guard(
            db, call, exclude_guard_ids=list(declined_ids)
        )

        if not next_guard:
            # No more guards available — cancel the call by system
            call.status = CallStatus.CANCELLED_BY_SYSTEM
            cancel_history = CallStatusHistory(
                call_id=call.id,
                status=CallStatus.CANCELLED_BY_SYSTEM,
                changed_by="system",
                meta_info=json.dumps({
                    "reason": "no_guards_available",
                    "total_declined": len(declined_ids),
                }),
            )
            db.add(cancel_history)

            # Notify the user that no guards are available
            if call.user_id:
                user_notification = Notification(
                    user_id=call.user_id,
                    title="Охрана недоступна",
                    body="К сожалению, все доступные охранники заняты. "
                         "Пожалуйста, попробуйте позже или позвоните 102.",
                    type="call_update",
                    data=json.dumps({
                        "call_id": call.id,
                        "status": "cancelled_by_system",
                    }),
                )
                db.add(user_notification)

            await db.flush()
            await db.refresh(call)

        return next_guard

    # ──────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────

    @classmethod
    async def _find_available_guards(
        cls,
        db: AsyncSession,
        call: EmergencyCall,
        exclude_ids: List[int],
    ) -> List[Guard]:
        """
        Query guards that are:
          - online (is_online = True)
          - not on another call (is_on_call = False)
          - active status
          - have a known location
          - belong to the call's company (if one is assigned)
          - not in the exclude list
        """
        conditions = [
            Guard.is_online == True,
            Guard.is_on_call == False,
            Guard.status == "active",
            Guard.current_latitude.isnot(None),
            Guard.current_longitude.isnot(None),
        ]

        # Scope to the assigned company if one exists
        if call.security_company_id:
            conditions.append(Guard.security_company_id == call.security_company_id)

        # Exclude previously declined guards
        if exclude_ids:
            conditions.append(Guard.id.notin_(exclude_ids))

        result = await db.execute(
            select(Guard)
            .options(selectinload(Guard.devices))
            .where(and_(*conditions))
        )
        return list(result.scalars().all())

    @classmethod
    async def _get_declined_guard_ids(cls, db: AsyncSession, call_id: int) -> set:
        """
        Parse the call's status history to find all guard IDs that declined.
        Returns a set of guard IDs.
        """
        result = await db.execute(
            select(CallStatusHistory.meta_info).where(
                CallStatusHistory.call_id == call_id,
                CallStatusHistory.changed_by == "guard",
            )
        )
        rows = result.scalars().all()

        declined_ids = set()
        for meta_raw in rows:
            if not meta_raw:
                continue
            try:
                meta = json.loads(meta_raw)
                if meta.get("action") == "declined" and meta.get("guard_id"):
                    declined_ids.add(meta["guard_id"])
            except (json.JSONDecodeError, TypeError):
                continue

        return declined_ids

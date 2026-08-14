"""
Dispatch engine for emergency call assignment and reassignment.

Handles:
  - Finding the nearest available guard for a call
  - Reassigning a call when a guard declines
  - Creating in-app notifications for guard call offers
  - Tracking which guards already declined a call
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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
from app.core.config import settings
from app.services.notifications import notification_service


logger = logging.getLogger(__name__)


#: Коды ошибок в теле ответа accept. Как и outside_service_area — контракт с
#: приложением охранника: по коду оно показывает конкретное объяснение, а не
#: общий текст ошибки. Менять только вместе с приложением.
GUARD_LOCATION_UNKNOWN_CODE = "guard_location_unknown"
GUARD_TOO_FAR_CODE = "guard_too_far_from_call"


@dataclass(frozen=True)
class GuardCallEligibility:
    """Может ли охранник взять вызов по географии: свежая позиция + радиус."""

    eligible: bool
    code: Optional[str] = None
    message: Optional[str] = None
    distance_km: Optional[float] = None

    def as_error_detail(self) -> dict:
        """Тело ответа для HTTPException — структурой, по образцу
        ServiceAreaCheck.as_error_detail: `code` читает приложение, `message`
        показывается человеку как есть."""
        return {
            "code": self.code,
            "message": self.message,
            "distance_km": round(self.distance_km, 1) if self.distance_km is not None else None,
        }


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
        5. If no guards available → call stays SEARCHING and a background
           retry keeps re-running dispatch until a guard frees up, someone
           accepts manually, or the call is closed
    """

    # Maximum distance in km to consider a guard "nearby". Read from settings on
    # every dispatch, not captured at import: the radius is an env var
    # (DISPATCH_MAX_SEARCH_RADIUS_KM) so it can be widened for another city or a
    # field test without a backend release.
    @classmethod
    def max_search_radius_km(cls) -> float:
        return settings.dispatch_max_search_radius_km

    # A guard's last known location is only trusted for dispatch if it was
    # reported within this window. Anything older is treated as "position
    # unknown" (e.g. the guard closed the app / lost signal), so the guard is
    # NOT considered a candidate and the call goes to the next truly-nearest
    # guard instead of to whoever happened to freeze closest when they quit.
    LOCATION_FRESHNESS_SECONDS = 180

    # Фоновый переподбор для вызова, оставшегося в SEARCHING: как часто
    # пере-сканировать пул охранников и сколько попыток делать. 45 × 20с ≈ 15
    # минут — дальше цикл гаснет, но вызов остаётся в SEARCHING: его всё ещё
    # видно в списке доступных, и админ может назначить группу вручную.
    RETRY_DISPATCH_INTERVAL_SECONDS = 20.0
    RETRY_DISPATCH_MAX_ATTEMPTS = 45

    # call_id вызовов, за которыми уже следит фоновый ретрай — на вызов не
    # больше одного цикла. In-memory набора достаточно: процесс один (uvicorn
    # без воркеров), ровно как у _schedule_broadcast_after_delay.
    _retry_dispatch_call_ids: set = set()

    @classmethod
    def location_is_fresh(cls, guard: Guard, now: Optional[datetime] = None) -> bool:
        """Есть ли у охранника позиция, которой диспетчер вправе верить."""
        if (
            guard.current_latitude is None
            or guard.current_longitude is None
            or guard.last_location_update is None
        ):
            return False
        last = guard.last_location_update
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        now = now or datetime.now(timezone.utc)
        return (now - last).total_seconds() <= cls.LOCATION_FRESHNESS_SECONDS

    @classmethod
    def check_guard_can_take(cls, guard: Guard, call: EmergencyCall) -> GuardCallEligibility:
        """География ручного взятия вызова — та же, что у автоназначения.

        Появилось после реального случая: диспетчер честно исключил охранника,
        которого числил в ~1000 км от вызова («0 candidates within 50.0km»),
        но вызов остался в SEARCHING, охранник увидел его в списке доступных и
        принял вручную — accept ничего не проверял, и приложение построило
        маршрут Актобе → Астана на ~19,5 часов. Ручной путь обязан играть по
        тем же правилам, что и автоматический: та же свежесть позиции
        (LOCATION_FRESHNESS_SECONDS) и тот же радиус (env
        DISPATCH_MAX_SEARCH_RADIUS_KM — им же этот гейт и ослабляется, если
        когда-нибудь начнёт мешать).
        """
        if not cls.location_is_fresh(guard):
            return GuardCallEligibility(
                eligible=False,
                code=GUARD_LOCATION_UNKNOWN_CODE,
                message=(
                    "Ваша геопозиция неизвестна или устарела — сервер не может "
                    "проверить, что вы рядом с вызовом. Проверьте, что GPS "
                    "включён и приложению разрешена геолокация."
                ),
            )
        distance_km = _haversine_km(
            call.latitude, call.longitude,
            guard.current_latitude, guard.current_longitude,
        )
        max_radius_km = cls.max_search_radius_km()
        if distance_km > max_radius_km:
            return GuardCallEligibility(
                eligible=False,
                code=GUARD_TOO_FAR_CODE,
                message=(
                    f"Вы в {distance_km:.0f} км от места вызова — дальше "
                    f"предела в {max_radius_km:.0f} км. Если ваша позиция на "
                    "карте неверна, проверьте GPS."
                ),
                distance_km=distance_km,
            )
        return GuardCallEligibility(eligible=True, distance_km=distance_km)

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

        logger.info(f"Dispatch: Found {len(candidates)} candidate guards for call {call.id}")

        if not candidates:
            return None

        # Sort by distance to the call location
        max_radius_km = cls.max_search_radius_km()
        candidates_with_dist = []
        for guard in candidates:
            if guard.current_latitude is not None and guard.current_longitude is not None:
                dist = _haversine_km(
                    call.latitude, call.longitude,
                    guard.current_latitude, guard.current_longitude,
                )
                if dist <= max_radius_km:
                    candidates_with_dist.append((guard, dist))
                else:
                    logger.debug(f"Dispatch: Guard {guard.id} too far ({dist:.1f}km)")

        logger.info(f"Dispatch: {len(candidates_with_dist)} candidates within {max_radius_km}km radius")

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

        # Schedule a background broadcast to other guards if this guard doesn't accept within 1 minute
        import asyncio
        asyncio.create_task(
            cls._schedule_broadcast_after_delay(call.id, chosen_guard.id, delay=60.0)
        )

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
            # Никого свободного прямо сейчас. Раньше вызов тут же гасился
            # CANCELLED_BY_SYSTEM («звоните 102»), хотя при создании SOS точно
            # такое же «никого нет» оставляет вызов в SEARCHING. Система не
            # вправе сама убивать живой SOS: вызов остаётся в поиске — виден
            # охранникам в списке доступных, — а фоновый ретрай переподбирает
            # группу, пока кто-то не освободится или вызов не закроют.
            cls.schedule_retry_dispatch(call.id)

        return next_guard

    @classmethod
    async def redirect_to_other_services(
        cls,
        db: AsyncSession,
        call: EmergencyCall,
        redirecting_guard: Guard,
        note: Optional[str] = None,
    ) -> Optional[Guard]:
        """
        Hand off an ACTIVE call to other security services.

        The guard currently handling the call redirects it: they are freed and
        excluded from re-assignment, the call is re-opened, the company scope is
        dropped so guards from ANY nearby company become eligible, and the offer
        is broadcast to the whole eligible pool immediately.

        Args:
            db: Database session
            call: The active emergency call being redirected
            redirecting_guard: The guard handing off the call
            note: Optional hand-off comment, surfaced to the next service and user

        Returns:
            The newly assigned Guard, or None if nobody else was available.
        """
        # Record the redirect in status history (also used to exclude this guard)
        history = CallStatusHistory(
            call_id=call.id,
            status=CallStatus.SEARCHING,
            changed_by="guard",
            meta_info=json.dumps({
                "action": "redirected",
                "guard_id": redirecting_guard.id,
                "guard_name": redirecting_guard.full_name,
                "note": note,
            }),
        )
        db.add(history)

        # Persist the hand-off note on the call so the next responder can read it
        if note:
            call.notes = note

        # Free the redirecting guard and re-open the call to ALL companies
        redirecting_guard.is_on_call = False
        call.guard_id = None
        call.security_company_id = None  # drop scope → nearest guard from any company
        call.status = CallStatus.SEARCHING

        # Exclude everyone who already declined/redirected this call (incl. current guard)
        excluded_ids = await cls._get_declined_guard_ids(db, call.id)
        excluded_ids.add(redirecting_guard.id)

        await db.flush()

        # Offer to the next nearest guard across all companies
        next_guard = await cls.assign_nearest_guard(
            db, call, exclude_guard_ids=list(excluded_ids)
        )

        if next_guard:
            # Broadcast to the rest of the eligible pool too — assign_nearest_guard
            # only pinged the single closest guard.
            other_candidates = await cls._find_available_guards(
                db, call=call, exclude_ids=list(excluded_ids) + [next_guard.id]
            )
            if other_candidates:
                await notification_service.broadcast_new_emergency(other_candidates, call)
        else:
            # Свободной группы прямо сейчас нет. Передача вызова не отменяет
            # вызов пользователя: раньше здесь ставился CANCELLED_BY_SYSTEM, и
            # человек в беде вместо «ищем новую группу» получал «вызов отменён
            # системой». Вызов остаётся в SEARCHING (открыт всем компаниям и
            # виден в списках доступных), а фоновый ретрай переподбирает
            # группу, пока кто-то не освободится или вызов не закроют.
            cls.schedule_retry_dispatch(call.id)

        # Notify the user: in-app record + live WS/FCM status update. Текст
        # один для обеих веток — вызов жив и группа ищется в любом случае.
        if call.user_id:
            note_suffix = f" Комментарий: {note}" if note else ""
            user_notification = Notification(
                user_id=call.user_id,
                title="Вызов перенаправлен",
                body=(
                    "Ваш вызов передан другой службе. Ищем ближайшего свободного "
                    f"сотрудника.{note_suffix}"
                ),
                type="call_update",
                data=json.dumps({
                    "call_id": call.id,
                    "status": "searching",
                    "redirected": True,
                }),
            )
            db.add(user_notification)
            await db.flush()

        # Push a live status update to the user (and the newly assigned guard)
        from app.services.emergency import EmergencyService
        refreshed = await EmergencyService.get_by_id(db, call.id)
        if refreshed:
            await notification_service.notify_call_status_update(refreshed)
            # Dedicated event so the user app shows a "redirected" UI rather
            # than a generic status change: диалог «вызов перенаправлен» и
            # возврат на экран поиска. Шлём в обеих ветках — и когда группа
            # нашлась сразу, и когда поиск продолжается в фоне.
            await notification_service.notify_call_redirected(refreshed, note=note)

        return next_guard

    @classmethod
    def schedule_retry_dispatch(cls, call_id: int) -> None:
        """Запустить фоновый переподбор группы для вызова в SEARCHING.

        Вызывается из веток «свободных охранников прямо сейчас нет» (создание
        SOS, decline, redirect). Идемпотентен: если за вызовом уже следит цикл,
        второй не создаётся — например, когда охранник отклонил оффер, который
        этот же цикл только что и разослал.
        """
        if call_id in cls._retry_dispatch_call_ids:
            return
        cls._retry_dispatch_call_ids.add(call_id)

        import asyncio
        asyncio.create_task(cls._retry_dispatch_loop(call_id))
        logger.info(f"Dispatch retry: scheduled background re-dispatch for call {call_id}")

    @classmethod
    async def _retry_dispatch_loop(cls, call_id: int):
        """Периодически пере-запускать подбор, пока вызов в SEARCHING.

        Без этого цикла вызов, оставшийся без группы, ждал бы только ручного
        принятия из списка доступных: освободившийся или вышедший на смену
        охранник сам никогда не «увидел» бы его оффером. Исключения — те же,
        что и везде (_get_declined_guard_ids): отказавшиеся и передавшие вызов
        группы повторно не дёргаются, но принять вручную из списка могут.
        """
        import asyncio
        from app.core.database import async_session

        try:
            for _ in range(cls.RETRY_DISPATCH_MAX_ATTEMPTS):
                await asyncio.sleep(cls.RETRY_DISPATCH_INTERVAL_SECONDS)

                async with async_session() as db:
                    result = await db.execute(
                        select(EmergencyCall)
                        .options(
                            selectinload(EmergencyCall.security_company),
                            selectinload(EmergencyCall.user),
                            selectinload(EmergencyCall.guard),
                        )
                        .where(EmergencyCall.id == call_id)
                    )
                    call = result.scalar_one_or_none()

                    # Вызов приняли, отменили или назначили вручную — цикл не нужен.
                    if not call or call.status != CallStatus.SEARCHING:
                        return

                    excluded = await cls._get_declined_guard_ids(db, call.id)
                    guard = await cls.assign_nearest_guard(
                        db, call, exclude_guard_ids=list(excluded)
                    )
                    if guard:
                        # Сессия фоновая, за нас никто не закоммитит (get_db
                        # делает это только в запросах).
                        await db.commit()
                        logger.info(
                            f"Dispatch retry: call {call_id} offered to guard "
                            f"{guard.id} after background re-dispatch"
                        )
                        return

            logger.warning(
                f"Dispatch retry: no guard found for call {call_id} after "
                f"{cls.RETRY_DISPATCH_MAX_ATTEMPTS} attempts — call stays in "
                f"SEARCHING for manual accept/assignment"
            )
        except Exception as e:
            logger.error(f"Dispatch retry: loop for call {call_id} failed: {e}", exc_info=True)
        finally:
            cls._retry_dispatch_call_ids.discard(call_id)

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
          - whose location is FRESH (reported within LOCATION_FRESHNESS_SECONDS)
          - within max_search_radius_km of the call
          - belong to the call's company (if one is assigned)
          - not in the exclude list
        """
        # Only trust a guard's coordinates if they were reported recently.
        # A guard who closed the app keeps is_online=True with frozen
        # coordinates; excluding stale fixes here means the SOS is routed by
        # the guard's *current* whereabouts, not where they were when they quit.
        fresh_cutoff = datetime.now(timezone.utc) - timedelta(
            seconds=cls.LOCATION_FRESHNESS_SECONDS
        )

        conditions = [
            Guard.is_online == True,
            Guard.is_on_call == False,
            Guard.status == "active",
            Guard.current_latitude.isnot(None),
            Guard.current_longitude.isnot(None),
            Guard.last_location_update.isnot(None),
            Guard.last_location_update >= fresh_cutoff,
        ]

        # Scope to the assigned company if one exists
        if call.security_company_id:
            conditions.append(Guard.security_company_id == call.security_company_id)

        # Exclude previously declined guards
        if exclude_ids:
            conditions.append(Guard.id.notin_(exclude_ids))

        result = await db.execute(
            select(Guard)
            .where(and_(*conditions))
        )
        guards = list(result.scalars().all())

        # Радиус — уже здесь, а не только в assign_nearest_guard: этим списком
        # пользуются и минутный ре-бродкаст, и redirect, и раньше они слали
        # сирену «Экстренный вызов» охранникам на любом расстоянии — в т.ч.
        # тем, кого автоназначение только что исключило как слишком далёких.
        max_radius_km = cls.max_search_radius_km()
        nearby = [
            g for g in guards
            if _haversine_km(
                call.latitude, call.longitude,
                g.current_latitude, g.current_longitude,
            ) <= max_radius_km
        ]
        dropped = len(guards) - len(nearby)
        if dropped:
            logger.info(
                f"Dispatch: {dropped} available guard(s) beyond "
                f"{max_radius_km}km of call {call.id} — not notified"
            )
        return nearby

    @classmethod
    async def _get_declined_guard_ids(cls, db: AsyncSession, call_id: int) -> set:
        """
        Parse the call's status history to find all guard IDs that should be
        excluded from (re)assignment — i.e. guards who declined an offer or
        redirected (handed off) the active call.
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
                if meta.get("action") in ("declined", "redirected") and meta.get("guard_id"):
                    declined_ids.add(meta["guard_id"])
            except (json.JSONDecodeError, TypeError):
                continue

        return declined_ids

    @classmethod
    async def _schedule_broadcast_after_delay(
        cls,
        call_id: int,
        initial_guard_id: int,
        delay: float = 60.0
    ):
        """
        Wait for `delay` seconds, then check if the call is still not accepted.
        If it's not accepted, broadcast the emergency to other available guards.
        """
        import asyncio
        from app.core.database import async_session
        from app.services.notifications import notification_service
        from sqlalchemy import select

        await asyncio.sleep(delay)

        try:
            async with async_session() as db:
                result = await db.execute(
                    select(EmergencyCall)
                    .options(
                        selectinload(EmergencyCall.security_company),
                        selectinload(EmergencyCall.user),
                        selectinload(EmergencyCall.guard)
                    )
                    .where(EmergencyCall.id == call_id)
                )
                call = result.scalar_one_or_none()

                if not call:
                    logger.warning(f"Dispatch background: Call {call_id} not found.")
                    return

                # If the call is no longer in OFFER_SENT status or is assigned to another guard, do nothing
                if call.status != CallStatus.OFFER_SENT or call.guard_id != initial_guard_id:
                    logger.info(f"Dispatch background: Call {call.id} is in state {call.status} (assigned to {call.guard_id}). No broadcast needed.")
                    return

                # Collect guards who have already declined this call
                declined_ids = await cls._get_declined_guard_ids(db, call.id)
                exclude_ids = list(declined_ids)
                if initial_guard_id not in exclude_ids:
                    exclude_ids.append(initial_guard_id)

                candidates = await cls._find_available_guards(
                    db,
                    call=call,
                    exclude_ids=exclude_ids,
                )

                if candidates:
                    logger.info(f"Dispatch background: Broadcasting call {call.id} to {len(candidates)} other guards after 1 minute.")
                    await notification_service.broadcast_new_emergency(candidates, call)
                else:
                    logger.info(f"Dispatch background: No other available guards to broadcast call {call.id} to.")
        except Exception as e:
            logger.error(f"Error in scheduled broadcast for call {call_id}: {e}", exc_info=True)

import logging
from typing import Optional, List, Tuple
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, desc, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import Guard, GuardShift, GuardSettings

logger = logging.getLogger(__name__)


class GuardService:
    """Service for guard management"""

    # A fix coarser than this is too imprecise to route a dispatch by — we keep
    # the last good position rather than jump the guard across the neighbourhood.
    MAX_LOCATION_ACCURACY_M = 100.0
    # …but a frozen point is worse than a rough one. Once the stored position is
    # older than this, a coarse fix is accepted anyway: routing from a real
    # position with honest accuracy beats refusing to route at all.
    STALE_AFTER_SECONDS = 120.0
    # A move faster than this between two accepted fixes is a GPS teleport, not
    # travel — reject it so the map doesn't flick to the wrong block and back.
    MAX_PLAUSIBLE_SPEED_KMH = 200.0
    # …but the speed test only means anything between fixes taken close together.
    # Across a longer gap (app closed, phone off overnight, a flight, a device
    # swap) any distance is plausible, and refusing the new fix would pin the
    # guard to a position we already know is worthless.
    TELEPORT_WINDOW_SECONDS = 300.0
    # A fix that claims to be older than this is not worth reasoning about.
    MAX_FIX_AGE_SECONDS = 3600.0

    # ── Самоизлечение от «запертой» неверной точки ──
    # Антителепорт-гейт защищает от одиночных выбросов GPS, но у него есть
    # обратная сторона, проявившаяся в проде: если БД держит неверную точку,
    # которую что-то продолжает освежать (мок-локация на тестовом устройстве,
    # зависший провайдер, шлющий один и тот же замороженный фикс), то настоящие
    # фиксы охранника отбрасываются как «телепорт» ВЕЧНО — окно в 300 с никогда
    # не истекает, и охранник в Астане числится в Актобе. Поэтому телепорт
    # перестаёт быть телепортом, когда несколько отклонённых фиксов ПОДРЯД
    # согласно указывают в одно и то же новое место: один выброс так себя не
    # ведёт, а реальный переезд — ровно так.
    RELOCATION_CONFIRM_FIXES = 3
    # Согласие фиксов между собой: каждый следующий не дальше этого от
    # предыдущего отклонённого (охранник может ехать, точки дрейфуют).
    RELOCATION_AGREE_RADIUS_M = 1000.0
    # Голоса старше этого забываются: три выброса за неделю — не переезд.
    RELOCATION_VOTE_TTL_SECONDS = 600.0

    # Память голосов на процесс: guard_id → (lat, lng, votes, last_at).
    # Один uvicorn-процесс на дино (см. Procfile), поэтому словаря достаточно;
    # при рестарте голоса накапливаются заново за пару минут — приемлемо.
    _relocation_votes: dict = {}

    # ── Демпфер: покинутая точка не голосует обратно ──
    # Без него два живых источника устраивают вечный пинг-понг: три настоящих
    # фикса переворачивают точку на новый город, после чего фиксы старого
    # источника сами становятся «телепортами», голосуют — и через минуту
    # переворачивают обратно. Поэтому после подтверждённого переезда точка,
    # которую мы покинули, попадает в чёрный список: телепорт-фиксы рядом с
    # ней не голосуют вовсе. Каждый такой фикс ПРОДЛЕВАЕТ список — пока
    # замороженный источник жив, он сам держит себя в блоке, а замолчит —
    # запись истечёт. Настоящее возвращение так не блокируется: непрерывно
    # ведомый охранник (позиция едет вместе с ним) телепортов не порождает,
    # а после долгой тишины (перелёт) фикс принимается в обход окна.
    ABANDONED_SUPPRESS_RADIUS_M = 2000.0
    ABANDONED_SUPPRESS_TTL_SECONDS = 900.0

    # guard_id → (lat, lng, last_seen_at) — покинутые при переезде точки.
    _abandoned_points: dict = {}

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[Guard]:
        """Get guard by email address"""
        result = await db.execute(
            select(Guard).where(Guard.email == email.lower())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(db: AsyncSession, guard_id: int) -> Optional[Guard]:
        """Get guard by ID"""
        result = await db.execute(
            select(Guard).where(Guard.id == guard_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_with_company(db: AsyncSession, guard_id: int) -> Optional[Guard]:
        """Get guard with company info"""
        result = await db.execute(
            select(Guard)
            .options(selectinload(Guard.security_company))
            .where(Guard.id == guard_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        db: AsyncSession,
        security_company_id: int,
        email: str,
        full_name: str,
        phone: Optional[str] = None,
        employee_id: Optional[str] = None
    ) -> Guard:
        """Create new guard (called by company admin)"""
        guard = Guard(
            security_company_id=security_company_id,
            email=email.lower(),
            phone=phone,
            full_name=full_name,
            employee_id=employee_id,
        )
        db.add(guard)
        await db.flush()

        # Create default settings
        settings = GuardSettings(guard_id=guard.id)
        db.add(settings)
        await db.flush()
        await db.refresh(guard)
        return guard

    @staticmethod
    async def update(db: AsyncSession, guard: Guard, data: dict) -> Guard:
        """Update guard profile"""
        for field, value in data.items():
            if value is not None:
                setattr(guard, field, value)
        await db.flush()
        await db.refresh(guard)
        return guard

    @staticmethod
    def _evaluate_fix(
        guard: Guard,
        latitude: float,
        longitude: float,
        accuracy: Optional[float],
        now: datetime,
    ) -> Tuple[str, str]:
        """Decide what to do with an incoming fix.

        Returns ``(verdict, reason)`` where verdict is one of:
          ``accept``   — store the coordinate and stamp it;
          ``confirm``  — same place, worse measurement: keep the stored coordinate
                         but stamp it, because the guard *was* just measured there;
          ``reject``   — garbage: change nothing and let the point age;
          ``teleport`` — implausible jump. Caller decides: a lone jump is a
                         reject, but several consistent ones are a relocation —
                         see ``_confirm_relocation``.

        The split matters: a rejected fix leaves ``last_location_update`` behind,
        and dispatch/routing read that stamp. Treating "no movement" as "no news"
        freezes a standing guard out of routing after the 10-minute gate, even
        though their phone is reporting every 60 s.
        """
        has_prev = (
            guard.current_latitude is not None
            and guard.current_longitude is not None
            and guard.last_location_update is not None
        )
        if not has_prev:
            return "accept", "first fix"

        prev_at = guard.last_location_update
        if prev_at.tzinfo is None:
            prev_at = prev_at.replace(tzinfo=timezone.utc)
        stored_age_s = (now - prev_at).total_seconds()

        # Фикс старше уже сохранённого (переотправка из очереди после потери
        # сети): позиция в БД новее, менять её по устаревшим данным нельзя.
        if stored_age_s < 0:
            return "reject", f"out-of-order fix ({-stored_age_s:.0f}s older than stored)"

        # 1. Coarse fix — cell/Wi-Fi or a cold GPS start. Normally not good enough
        #    to route by, BUT never at the price of freezing the point: once the
        #    stored position has gone stale, a rough current position beats a
        #    precise obsolete one (its accuracy is stored and shown in the UI).
        if accuracy is not None and accuracy > GuardService.MAX_LOCATION_ACCURACY_M:
            if stored_age_s >= GuardService.STALE_AFTER_SECONDS:
                return "accept", (
                    f"coarse {accuracy:.0f}m accepted — stored fix {stored_age_s:.0f}s stale"
                )
            return "reject", f"accuracy {accuracy:.0f}m > {GuardService.MAX_LOCATION_ACCURACY_M:.0f}m"

        from app.services.routing import _haversine_km
        dist_m = _haversine_km(
            guard.current_latitude, guard.current_longitude, latitude, longitude
        ) * 1000.0

        # 2. Teleport — implausible speed vs the last *accepted* fix (not the last
        #    ping, so a rejected fix can't skew the time base). Only judged inside
        #    the window where "too fast" still means "impossible": past it the
        #    stored point is stale, and holding on to it would strand a guard whose
        #    phone was off — or who moved cities — at their last known spot.
        if 0 <= stored_age_s <= GuardService.TELEPORT_WINDOW_SECONDS:
            # Не меньше секунды: раньше `0 < stored_age_s` пропускал БЕЗ
            # проверки два фикса, пришедшие в одну секунду, — телепорт на
            # тысячу километров проходил, если успевал в ту же секунду, что
            # и предыдущий фикс.
            speed_kmh = (dist_m / 1000.0) / (max(stored_age_s, 1.0) / 3600.0)
            if speed_kmh > GuardService.MAX_PLAUSIBLE_SPEED_KMH:
                return "teleport", f"anomalous speed {speed_kmh:.0f} km/h ({dist_m / 1000.0:.1f} km)"

        # 3. Jitter — a barely-there move reported by a *less* accurate fix is noise,
        #    not travel. Keep the tighter position, but treat it as confirmed: we
        #    just measured the guard inside the radius we already had.
        prev_acc = guard.current_accuracy
        if (
            accuracy is not None
            and prev_acc is not None
            and accuracy > prev_acc
            and dist_m <= prev_acc
        ):
            return "confirm", f"jitter ({dist_m:.0f}m within prior {prev_acc:.0f}m, worse fix {accuracy:.0f}m)"

        return "accept", "accepted"

    @classmethod
    def _confirm_relocation(cls, guard: Guard, latitude: float, longitude: float, now: datetime) -> bool:
        """Голосование отклонённых «телепортов» за то, что охранник правда
        переместился. True — подряд RELOCATION_CONFIRM_FIXES фиксов согласно
        указывают в новое место, пора верить им, а не сохранённой точке.

        Якорь голосования — ПОСЛЕДНИЙ отклонённый фикс (цепочка): охранник в
        новом городе движется, и требовать попадания всех фиксов в один круг
        значило бы не подтвердить переезд никогда. Выброс дальше километра от
        цепочки начинает голосование заново — случайные глюки GPS так и
        рассыпаются, не дойдя до порога.
        """
        from app.services.routing import _haversine_km

        guard_id = guard.id

        # Демпфер: фикс, указывающий в недавно покинутую точку, не голосует —
        # и продлевает её блок (см. комментарий у ABANDONED_SUPPRESS_*).
        abandoned = cls._abandoned_points.get(guard_id)
        if abandoned is not None:
            a_lat, a_lng, a_at = abandoned
            if (now - a_at).total_seconds() > cls.ABANDONED_SUPPRESS_TTL_SECONDS:
                cls._abandoned_points.pop(guard_id, None)
            elif _haversine_km(a_lat, a_lng, latitude, longitude) * 1000.0 \
                    <= cls.ABANDONED_SUPPRESS_RADIUS_M:
                cls._abandoned_points[guard_id] = (a_lat, a_lng, now)
                return False

        prev = cls._relocation_votes.get(guard_id)
        votes = 1
        if prev is not None:
            p_lat, p_lng, p_votes, p_at = prev
            fresh = (now - p_at).total_seconds() <= cls.RELOCATION_VOTE_TTL_SECONDS
            agrees = _haversine_km(p_lat, p_lng, latitude, longitude) * 1000.0 \
                <= cls.RELOCATION_AGREE_RADIUS_M
            if fresh and agrees:
                votes = p_votes + 1
        if votes >= cls.RELOCATION_CONFIRM_FIXES:
            cls._relocation_votes.pop(guard_id, None)
            # Точка, которую покидаем, — в чёрный список: ей нельзя тут же
            # выголосовать себя назад.
            if guard.current_latitude is not None and guard.current_longitude is not None:
                cls._abandoned_points[guard_id] = (
                    guard.current_latitude, guard.current_longitude, now,
                )
            return True
        cls._relocation_votes[guard_id] = (latitude, longitude, votes, now)
        return False

    @staticmethod
    async def update_location(
        db: AsyncSession,
        guard: Guard,
        latitude: float,
        longitude: float,
        accuracy: Optional[float] = None,
        fix_age_seconds: float = 0.0,
    ) -> Guard:
        """Update guard's real-time location.

        Every ping bumps ``last_seen`` (liveness). A coordinate is stored — and
        ``last_location_update`` bumped — only when the fix passes quality checks.
        This keeps the dispatch freshness gate honest: a guard sending garbage
        fixes goes *stale*, rather than looking fresh while pinned to an old spot.

        A fix that merely re-measures the same spot less precisely is not garbage:
        it confirms the stored position, so the stamp is refreshed while the
        coordinate (and its better accuracy) is kept.

        ``last_location_update`` — возраст ПОЗИЦИИ, а не запроса: как и у
        пользователя, штамп ставится моментом получения фикса GPS (``now`` минус
        ``fix_age_seconds``, относительное значение — сбитые часы устройства его
        не отравят). Диспетчер и маршрутизация читают этот штамп, поэтому
        телефон, переотправляющий из очереди фикс десятиминутной давности, не
        должен выглядеть свежим.
        """
        now = datetime.now(timezone.utc)

        # Liveness first — the device is talking to us regardless of fix quality.
        guard.last_seen = now

        age = min(max(fix_age_seconds or 0.0, 0.0), GuardService.MAX_FIX_AGE_SECONDS)
        fix_time = now - timedelta(seconds=age)

        verdict, reason = GuardService._evaluate_fix(guard, latitude, longitude, accuracy, fix_time)

        if verdict == "teleport":
            if GuardService._confirm_relocation(guard, latitude, longitude, now):
                verdict = "accept"
                # INFO: смена города охранником — редкое и диагностически важное
                # событие; в проде оно должно быть видно.
                logger.info(
                    f"Guard {guard.id} relocation confirmed by "
                    f"{GuardService.RELOCATION_CONFIRM_FIXES} consistent fixes — "
                    f"accepting ({latitude:.5f}, {longitude:.5f}) over stored "
                    f"({guard.current_latitude:.5f}, {guard.current_longitude:.5f})"
                )
            else:
                # Тоже INFO, не DEBUG: в проде Heroku пишет только INFO, и
                # прошлый инцидент (настоящие фиксы месяцами отбрасывались в
                # пользу мок-точки) в логах было попросту не видно.
                logger.info(f"Guard {guard.id} location fix rejected ({reason})")
                await db.flush()
                return guard
        elif verdict == "reject":
            logger.debug(f"Guard {guard.id} location fix rejected ({reason})")
            await db.flush()
            return guard
        # Принятые фиксы голосование НЕ гасят — сознательно. В инциденте два
        # источника слали вперемешку: мок-точка (принимается, расстояние 0) и
        # настоящая (отклоняется как телепорт). Если бы каждый принятый фикс
        # обнулял счётчик, настоящие никогда не набрали бы порог. Голоса и так
        # ограничены TTL и цепочкой согласия в _confirm_relocation.

        if verdict == "accept":
            guard.current_latitude = latitude
            guard.current_longitude = longitude
            guard.current_accuracy = accuracy
        else:
            # "confirm": same place, worse measurement — keep the coordinate and
            # its accuracy, refresh only the timestamp.
            logger.debug(f"Guard {guard.id} position confirmed in place ({reason})")
        guard.last_location_update = fix_time

        await db.flush()

        # ── Broadcast guard location to the user of the active call ──
        try:
            from sqlalchemy import select, desc
            from app.models import EmergencyCall, CallStatus
            active_statuses = [
                CallStatus.ACCEPTED,
                CallStatus.EN_ROUTE,
                CallStatus.ARRIVED,
            ]
            result = await db.execute(
                select(EmergencyCall)
                .where(
                    EmergencyCall.guard_id == guard.id,
                    EmergencyCall.status.in_(active_statuses),
                )
                .order_by(desc(EmergencyCall.created_at))
                .limit(1)
            )
            active_call = result.scalar_one_or_none()

            if active_call and active_call.user_id:
                from app.api.ws.manager import manager
                # Broadcast what is actually stored — on "confirm" the incoming
                # coordinate was discarded as noise, so sending it would move the
                # guard's dot by exactly the jitter we just filtered out.
                await manager.send_to_user(active_call.user_id, {
                    "type": "guard_location_update",
                    "call_id": active_call.id,
                    "latitude": guard.current_latitude,
                    "longitude": guard.current_longitude,
                })
                logger.debug(
                    f"WS: Sent guard location ({guard.current_latitude}, "
                    f"{guard.current_longitude}) to user {active_call.user_id} "
                    f"for call {active_call.id}"
                )
        except Exception as e:
            # Never fail the location update because of a WS error
            logger.warning(f"WS: Failed to broadcast guard location to user: {e}")

        return guard

    @staticmethod
    async def delete(db: AsyncSession, guard: Guard) -> bool:
        """Deactivate guard (soft delete)"""
        guard.status = "inactive"
        guard.is_online = False
        await db.flush()
        return True

    @staticmethod
    async def list_by_company(
        db: AsyncSession,
        company_id: int,
        limit: int = 50,
        offset: int = 0,
        search: Optional[str] = None
    ) -> tuple[List[Guard], int]:
        """List guards by company (for admin)"""
        query = select(Guard).where(Guard.security_company_id == company_id)

        if search:
            query = query.where(
                Guard.full_name.ilike(f"%{search}%") |
                Guard.email.ilike(f"%{search}%")
            )

        # Count
        count_query = select(sa_func.count()).select_from(query.subquery())
        count_result = await db.execute(count_query)
        total = count_result.scalar()

        # Fetch
        result = await db.execute(
            query.order_by(desc(Guard.created_at))
            .offset(offset)
            .limit(limit)
        )
        guards = result.scalars().all()
        return list(guards), total

    @staticmethod
    async def get_online_by_company(
        db: AsyncSession,
        company_id: int
    ) -> List[Guard]:
        """Get all online guards for a company"""
        result = await db.execute(
            select(Guard).where(
                Guard.security_company_id == company_id,
                Guard.is_online == True,
                Guard.status == "active"
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_rating(db: AsyncSession, guard: Guard) -> Guard:
        """Recalculate guard's average rating from reviews"""
        from app.models import Review
        result = await db.execute(
            select(
                sa_func.avg(Review.rating),
                sa_func.count(Review.id)
            ).where(Review.guard_id == guard.id)
        )
        row = result.one()
        avg_rating, count = row
        guard.rating = round(float(avg_rating), 2) if avg_rating else 5.0
        guard.total_reviews = count or 0
        await db.flush()
        return guard

    @staticmethod
    async def update_fcm_token(
        db: AsyncSession,
        guard: Guard,
        fcm_token: Optional[str]
    ) -> Guard:
        """Update guard's FCM token for push notifications"""
        guard.fcm_token = fcm_token
        await db.flush()
        await db.refresh(guard)
        return guard

    @staticmethod
    async def get_all_fcm_tokens(db: AsyncSession) -> List[str]:
        """Get all unique FCM tokens for guards"""
        result = await db.execute(
            select(Guard.fcm_token).where(Guard.fcm_token.isnot(None))
        )
        return [str(token) for token in result.scalars().all() if token]


class GuardShiftService:
    """Service for guard shift management"""

    @staticmethod
    async def start_shift(db: AsyncSession, guard: Guard) -> GuardShift:
        """Start a new shift (go online)"""
        guard.is_online = True
        shift = GuardShift(guard_id=guard.id)
        db.add(shift)
        await db.flush()
        await db.refresh(shift)
        return shift

    @staticmethod
    async def end_shift(db: AsyncSession, guard: Guard) -> Optional[GuardShift]:
        """End current shift (go offline)"""
        guard.is_online = False
        guard.is_on_call = False

        # Find active shift
        result = await db.execute(
            select(GuardShift).where(
                GuardShift.guard_id == guard.id,
                GuardShift.ended_at.is_(None)
            ).order_by(desc(GuardShift.started_at)).limit(1)
        )
        shift = result.scalar_one_or_none()

        if shift:
            now = datetime.now(timezone.utc)
            shift.ended_at = now
            if shift.started_at:
                shift.duration_minutes = int((now - shift.started_at).total_seconds() / 60)
            await db.flush()
            await db.refresh(shift)

        return shift

    @staticmethod
    async def get_current_shift(db: AsyncSession, guard_id: int) -> Optional[GuardShift]:
        """Get active shift for guard"""
        result = await db.execute(
            select(GuardShift).where(
                GuardShift.guard_id == guard_id,
                GuardShift.ended_at.is_(None)
            ).order_by(desc(GuardShift.started_at)).limit(1)
        )
        return result.scalar_one_or_none()


class GuardSettingsService:
    """Service for guard settings"""

    @staticmethod
    async def get_or_create(db: AsyncSession, guard_id: int) -> GuardSettings:
        """Get settings or create defaults"""
        result = await db.execute(
            select(GuardSettings).where(GuardSettings.guard_id == guard_id)
        )
        settings = result.scalar_one_or_none()
        if not settings:
            settings = GuardSettings(guard_id=guard_id)
            db.add(settings)
            await db.flush()
            await db.refresh(settings)
        return settings

    @staticmethod
    async def update(db: AsyncSession, settings: GuardSettings, data: dict) -> GuardSettings:
        """Update settings"""
        for field, value in data.items():
            if value is not None:
                setattr(settings, field, value)
        await db.flush()
        await db.refresh(settings)
        return settings

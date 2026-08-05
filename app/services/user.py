from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models import User, Subscription, SubscriptionStatus
from app.schemas import UserCreate, UserUpdate


class UserService:
    """Service for user management"""

    # Quality bar for a fix we are happy to route by. A phone with GNSS on and a
    # clear-ish sky reports 3–20 m; anything past this bar is a cell/Wi-Fi or
    # cold-start fix that would move the caller across the block.
    MAX_LOCATION_ACCURACY_M = 35.0
    # …but a frozen point is worse than a rough one. Once the stored position is
    # older than this, a coarse fix is accepted anyway (its accuracy is stored
    # and surfaced in the UI, so the operator sees the real uncertainty instead
    # of a confident dot in the wrong place).
    STALE_AFTER_SECONDS = 20.0
    # Position is considered "live" (no staleness warning) below this age.
    FRESH_LOCATION_SECONDS = 30.0
    # A move faster than this between two accepted fixes is a GPS teleport, not
    # travel — reject it so the guard's map target doesn't flick and snap back.
    MAX_PLAUSIBLE_SPEED_KMH = 200.0
    # A fix that claims to be older than this is not worth reasoning about.
    MAX_FIX_AGE_SECONDS = 3600.0

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email address"""
        result = await db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """Get user by ID"""
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_with_subscription(db: AsyncSession, user_id: int) -> Optional[User]:
        """Get user with subscription data"""
        result = await db.execute(
            select(User)
            .options(selectinload(User.subscription))
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create(db: AsyncSession, email: str) -> User:
        """Create new user"""
        user = User(email=email.lower(), is_verified=True, is_new=True)
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user
    
    @staticmethod
    async def update(db: AsyncSession, user: User, data: UserUpdate) -> User:
        """Update user data"""
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        
        # If user updates full_name or phone, they are no longer "new"
        if "full_name" in update_data or "phone" in update_data:
            user.is_new = False
            
        await db.flush()
        await db.refresh(user)
        return user
    
    @staticmethod
    def _evaluate_fix(
        user: User,
        latitude: float,
        longitude: float,
        accuracy: Optional[float],
        fix_time: datetime,
    ) -> Tuple[str, str]:
        """Decide what to do with an incoming user fix.

        Returns ``(verdict, reason)`` where verdict is one of:

        * ``"accept"``  — store the coordinate and stamp it with ``fix_time``;
        * ``"confirm"`` — the caller has demonstrably NOT moved (the new fix is
          noise around the stored one), so keep the coordinate but stamp it fresh.
          Without this a motionless caller would drift into "position is stale"
          while we actually know exactly where they are;
        * ``"reject"``  — garbage; change nothing, and let the position age so the
          operator sees the truth ("устарела N мин назад") instead of a confident
          dot in a place the caller may have left long ago.

        ``fix_time`` is when the GPS produced the fix, not when the request landed —
        a phone that keeps resending its last known fix (GPS lost, app alive) must
        not look fresh.
        """
        has_prev = (
            user.last_latitude is not None
            and user.last_longitude is not None
            and user.last_location_update is not None
        )
        if not has_prev:
            return "accept", "first fix"

        prev_at = user.last_location_update
        if prev_at.tzinfo is None:
            prev_at = prev_at.replace(tzinfo=timezone.utc)
        stored_age_s = (fix_time - prev_at).total_seconds()

        # 0. Out-of-order delivery — a retry carrying an older fix than the one we
        #    already stored must not walk the point backwards.
        if stored_age_s < 0:
            return "reject", f"out-of-order fix ({-stored_age_s:.0f}s older than stored)"

        # 1. Coarse fix — cell/Wi-Fi or a cold GPS start. Normally not good enough
        #    to route by, BUT never at the price of freezing the point: once the
        #    stored position has gone stale, a rough current position beats a
        #    precise obsolete one (its accuracy is stored and shown in the UI).
        if accuracy is not None and accuracy > UserService.MAX_LOCATION_ACCURACY_M:
            if stored_age_s >= UserService.STALE_AFTER_SECONDS:
                return "accept", (
                    f"coarse {accuracy:.0f}m accepted — stored fix {stored_age_s:.0f}s stale"
                )
            return "reject", f"accuracy {accuracy:.0f}m > {UserService.MAX_LOCATION_ACCURACY_M:.0f}m"

        from app.services.routing import _haversine_km
        dist_m = _haversine_km(
            user.last_latitude, user.last_longitude, latitude, longitude
        ) * 1000.0

        # 2. Teleport — implausible speed vs the last *accepted* fix (not the last
        #    ping, so a rejected fix can't skew the time base).
        if stored_age_s > 0:
            speed_kmh = (dist_m / 1000.0) / (stored_age_s / 3600.0)
            if speed_kmh > UserService.MAX_PLAUSIBLE_SPEED_KMH:
                return "reject", f"anomalous speed {speed_kmh:.0f} km/h"

        # 3. Jitter — a barely-there move reported by a *less* accurate fix is noise,
        #    not travel. Keep the tighter position, but treat it as confirmed: we
        #    just measured the caller inside the radius we already had.
        prev_acc = user.current_accuracy
        if (
            accuracy is not None
            and prev_acc is not None
            and accuracy > prev_acc
            and dist_m <= prev_acc
        ):
            return "confirm", f"jitter ({dist_m:.0f}m within prior {prev_acc:.0f}m, worse fix {accuracy:.0f}m)"

        return "accept", "accepted"

    @staticmethod
    async def update_location(
        db: AsyncSession,
        user: User,
        latitude: float,
        longitude: float,
        accuracy: Optional[float] = None,
        fix_age_seconds: float = 0.0,
    ) -> User:
        """Update the user's last known location and broadcast it to the assigned
        guard during an active call.

        ``last_location_update`` is the age of the POSITION, not of the request:
        it is stamped with the moment the GPS produced the fix (``now`` minus
        ``fix_age_seconds``, a relative value so a skewed device clock can't poison
        it). Everything downstream — the guard's route, the operator's map, the
        "устарела N мин назад" badge — reads that stamp, so a phone that keeps
        re-POSTing a fix from ten minutes ago must not look current.

        A rejected fix changes nothing at all: the position is left to age, which
        is what surfaces the warning. Silently swapping in some other coordinate
        would hide exactly the failure the operator needs to see.
        """
        import logging
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select, desc
        from app.models import EmergencyCall, CallStatus

        logger = logging.getLogger(__name__)
        now = datetime.now(timezone.utc)
        age = min(max(fix_age_seconds or 0.0, 0.0), UserService.MAX_FIX_AGE_SECONDS)
        fix_time = now - timedelta(seconds=age)

        verdict, reason = UserService._evaluate_fix(
            user, latitude, longitude, accuracy, fix_time
        )
        if verdict == "reject":
            logger.debug(f"User {user.id} location fix rejected ({reason})")
            return user

        if verdict == "accept":
            user.last_latitude = latitude
            user.last_longitude = longitude
            user.current_accuracy = accuracy
        else:
            # "confirm": same place, worse measurement — keep the coordinate and
            # its accuracy, refresh only the timestamp.
            logger.debug(f"User {user.id} position confirmed in place ({reason})")
        user.last_location_update = fix_time
        await db.flush()

        # ── Broadcast location to guard if there is an active call ──
        try:
            active_statuses = [
                CallStatus.ACCEPTED,
                CallStatus.EN_ROUTE,
                CallStatus.ARRIVED,
            ]
            result = await db.execute(
                select(EmergencyCall)
                .where(
                    EmergencyCall.user_id == user.id,
                    EmergencyCall.status.in_(active_statuses),
                    EmergencyCall.guard_id.isnot(None),
                )
                .order_by(desc(EmergencyCall.created_at))
                .limit(1)
            )
            active_call = result.scalar_one_or_none()

            if active_call and active_call.guard_id:
                from app.api.ws.manager import manager
                # Broadcast what is actually stored (on "confirm" the incoming
                # coordinate was discarded as noise) plus the age of the fix, so
                # the guard app can age the point instead of assuming "just now".
                await manager.send_to_guard(active_call.guard_id, {
                    "type": "user_location_update",
                    "call_id": active_call.id,
                    "latitude": user.last_latitude,
                    "longitude": user.last_longitude,
                    "accuracy": user.current_accuracy,
                    "age_seconds": round(age, 1),
                })
                logger.debug(
                    f"WS: Sent user location ({user.last_latitude}, {user.last_longitude}) "
                    f"to guard {active_call.guard_id} for call {active_call.id}"
                )
        except Exception as e:
            # Never fail the location update because of a WS error
            logger.warning(f"WS: Failed to broadcast user location to guard: {e}")

        return user
    
    @staticmethod
    async def has_active_subscription(db: AsyncSession, user_id: int) -> bool:
        """Check if user has a currently-active subscription.

        Honors `expires_at`: an ACTIVE row whose period has already passed does
        NOT count (a daily job flips such rows to EXPIRED, but access must end at
        the expiry instant regardless of when that job runs).
        """
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                or_(
                    Subscription.expires_at.is_(None),
                    Subscription.expires_at > now,
                ),
            )
        )
        subscription = result.scalar_one_or_none()
        return subscription is not None
    
    @staticmethod
    async def delete(db: AsyncSession, user: User) -> bool:
        """Delete user account"""
        await db.delete(user)
        return True

    @staticmethod
    async def update_fcm_token(
        db: AsyncSession,
        user: User,
        fcm_token: Optional[str]
    ) -> User:
        """Update user's FCM token for push notifications"""
        user.fcm_token = fcm_token
        await db.flush()
        await db.refresh(user)
        return user

    @staticmethod
    async def get_all_fcm_tokens(db: AsyncSession) -> List[str]:
        """Get all unique FCM tokens for users"""
        result = await db.execute(
            select(User.fcm_token).where(User.fcm_token.isnot(None))
        )
        return [str(token) for token in result.scalars().all() if token]

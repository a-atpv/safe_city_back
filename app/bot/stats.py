"""Numbers behind the bot's /stats command.

Windows are rolling ("last 24h/7d/30d") rather than calendar days on purpose:
the dyno runs in UTC while the business reads them in UTC+5, and a rolling
window means the same number regardless of which timezone you ask from.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, Subscription, SubscriptionStatus, User


@dataclass
class Stats:
    users_total: int
    users_24h: int
    users_7d: int
    users_30d: int
    subs_active: int
    subs_auto_renew: int
    subs_expiring_7d: int
    subs_by_plan: dict
    payments_total: int
    revenue_total_tiyn: int
    payments_30d: int
    revenue_30d_tiyn: int
    generated_at: datetime


async def _scalar(db: AsyncSession, stmt) -> int:
    return (await db.execute(stmt)).scalar() or 0


async def collect(db: AsyncSession) -> Stats:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # "Active" mirrors UserService.has_active_subscription: an ACTIVE row whose
    # period already passed does not count, even before the daily job expires it.
    active_filter = (
        Subscription.status == SubscriptionStatus.ACTIVE,
        or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
    )

    by_plan = (
        await db.execute(
            select(Subscription.plan_type, func.count(Subscription.id))
            .where(*active_filter)
            .group_by(Subscription.plan_type)
        )
    ).all()

    return Stats(
        users_total=await _scalar(db, select(func.count(User.id))),
        users_24h=await _scalar(
            db, select(func.count(User.id)).where(User.created_at >= day_ago)
        ),
        users_7d=await _scalar(
            db, select(func.count(User.id)).where(User.created_at >= week_ago)
        ),
        users_30d=await _scalar(
            db, select(func.count(User.id)).where(User.created_at >= month_ago)
        ),
        subs_active=await _scalar(
            db, select(func.count(Subscription.id)).where(*active_filter)
        ),
        subs_auto_renew=await _scalar(
            db,
            select(func.count(Subscription.id)).where(
                *active_filter, Subscription.auto_renew.is_(True)
            ),
        ),
        subs_expiring_7d=await _scalar(
            db,
            select(func.count(Subscription.id)).where(
                *active_filter, Subscription.expires_at <= now + timedelta(days=7)
            ),
        ),
        subs_by_plan={plan or "—": count for plan, count in by_plan},
        payments_total=await _scalar(
            db, select(func.count(Payment.id)).where(Payment.status == "success")
        ),
        revenue_total_tiyn=await _scalar(
            db, select(func.sum(Payment.amount)).where(Payment.status == "success")
        ),
        payments_30d=await _scalar(
            db,
            select(func.count(Payment.id)).where(
                Payment.status == "success", Payment.paid_at >= month_ago
            ),
        ),
        revenue_30d_tiyn=await _scalar(
            db,
            select(func.sum(Payment.amount)).where(
                Payment.status == "success", Payment.paid_at >= month_ago
            ),
        ),
        generated_at=now,
    )

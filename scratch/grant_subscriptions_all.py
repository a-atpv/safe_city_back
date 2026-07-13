"""One-off: grant an ACTIVE monthly subscription to every user.

Idempotent — creates a Subscription for users who have none, and (re)activates
existing ones. Mirrors PaymentService._activate_subscription: extends from the
later of now / current expiry so re-running never shrinks an active period.
"""
import asyncio
from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
from sqlalchemy import select

from app.core.database import async_session
from app.core.plans import get_plan
from app.models import User, Subscription
from app.models.user import SubscriptionStatus

PLAN_CODE = "monthly"


async def main() -> None:
    plan = get_plan(PLAN_CODE)
    months = plan.period_months if plan else 1
    price = plan.price_tiyn if plan else None
    now = datetime.now(timezone.utc)

    created = 0
    updated = 0

    async with async_session() as db:
        users = (await db.execute(select(User))).scalars().all()
        for user in users:
            sub = (
                await db.execute(
                    select(Subscription).where(Subscription.user_id == user.id)
                )
            ).scalar_one_or_none()

            if sub is None:
                sub = Subscription(user_id=user.id, started_at=now)
                db.add(sub)
                created += 1
            else:
                updated += 1

            base = sub.expires_at if (sub.expires_at and sub.expires_at > now) else now
            sub.status = SubscriptionStatus.ACTIVE
            sub.plan_type = PLAN_CODE
            sub.price = price
            if not sub.started_at:
                sub.started_at = now
            sub.expires_at = base + relativedelta(months=months)
            sub.cancelled_at = None
            sub.payment_provider = "manual_grant"

        await db.commit()

    print(
        f"Done. users={len(users)} created={created} updated={updated} "
        f"plan={PLAN_CODE} expires≈{(now + relativedelta(months=months)).date()}"
    )


if __name__ == "__main__":
    asyncio.run(main())

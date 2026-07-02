"""Payment orchestration: create Robokassa invoices and process callbacks.

This is the DB-facing layer. Pure Robokassa protocol lives in `robokassa.py`.
The single source of truth for a successful payment is the ResultURL callback
(`handle_successful_result`); SuccessURL is UX only and never grants access.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plans import get_plan
from app.models import Payment, Subscription, SubscriptionStatus, User
from app.services import robokassa

logger = logging.getLogger(__name__)


class PaymentService:
    @staticmethod
    async def _get_or_create_subscription(db: AsyncSession, user_id: int, plan) -> Subscription:
        sub = (
            await db.execute(select(Subscription).where(Subscription.user_id == user_id))
        ).scalar_one_or_none()
        if sub is None:
            sub = Subscription(
                user_id=user_id,
                status=SubscriptionStatus.PENDING,
                plan_type=plan.code,
                price=plan.price_tiyn,
            )
            db.add(sub)
            await db.flush()
        return sub

    @staticmethod
    async def create_subscription_payment(
        db: AsyncSession, user: User, plan_code: str, recurring: bool = True
    ) -> Tuple[Payment, str]:
        """Create a pending Payment and return it together with the Robokassa URL.

        The Payment's own id is used as the Robokassa InvId (unique per shop).
        """
        plan = get_plan(plan_code)
        if plan is None:
            raise ValueError(f"Unknown plan: {plan_code}")

        sub = await PaymentService._get_or_create_subscription(db, user.id, plan)
        payment = Payment(
            user_id=user.id,
            subscription_id=sub.id,
            amount=plan.price_tiyn,
            currency="KZT",
            status="pending",
            payment_method="card",
            plan_type=plan.code,
            is_recurring=recurring,
            description=plan.title,
        )
        db.add(payment)
        await db.flush()  # assign payment.id -> Robokassa InvId

        url = robokassa.build_payment_url(
            inv_id=payment.id,
            amount_tiyn=plan.price_tiyn,
            description=plan.title,
            email=user.email,
            recurring=recurring,
            receipt_name=plan.title,
        )
        await db.commit()
        await db.refresh(payment)
        logger.info(
            "Created payment inv=%s user=%s plan=%s amount=%s recurring=%s",
            payment.id, user.id, plan.code, plan.price_tiyn, recurring,
        )
        return payment, url

    @staticmethod
    async def handle_successful_result(
        db: AsyncSession, out_sum: str, inv_id: str, signature: str
    ) -> Optional[Payment]:
        """Validate a ResultURL callback and activate the subscription. Idempotent.

        Returns the Payment on success, or None if the callback is invalid
        (bad signature / unknown invoice / amount mismatch).
        """
        if not robokassa.verify_result_signature(out_sum, inv_id, signature):
            logger.warning("Robokassa result: bad signature inv=%s", inv_id)
            return None
        try:
            payment = await db.get(Payment, int(inv_id))
        except (TypeError, ValueError):
            return None
        if payment is None:
            logger.warning("Robokassa result: unknown inv=%s", inv_id)
            return None
        if not robokassa.amounts_equal(out_sum, payment.amount):
            logger.warning(
                "Robokassa result: amount mismatch inv=%s got=%s expected_tiyn=%s",
                inv_id, out_sum, payment.amount,
            )
            return None
        if payment.status == "success":
            return payment  # duplicate callback — already processed

        payment.status = "success"
        payment.paid_at = datetime.now(timezone.utc)
        await PaymentService._activate_subscription(db, payment)
        await db.commit()
        logger.info("Payment success inv=%s user=%s", payment.id, payment.user_id)
        return payment

    @staticmethod
    async def _activate_subscription(db: AsyncSession, payment: Payment) -> None:
        if not payment.subscription_id:
            return
        sub = await db.get(Subscription, payment.subscription_id)
        if sub is None:
            return
        now = datetime.now(timezone.utc)
        # Extend from the later of "now" and the current expiry so paying early never burns time.
        base = sub.expires_at if (sub.expires_at and sub.expires_at > now) else now
        plan = get_plan(payment.plan_type or sub.plan_type or "monthly")
        months = plan.period_months if plan else 1

        sub.status = SubscriptionStatus.ACTIVE
        sub.plan_type = payment.plan_type or sub.plan_type
        sub.price = payment.amount
        if not sub.started_at:
            sub.started_at = now
        sub.expires_at = base + relativedelta(months=months)
        sub.payment_provider = "robokassa"
        # Anchor for future recurring charges = the first (parent) invoice id.
        sub.external_subscription_id = str(payment.parent_inv_id or payment.id)

    @staticmethod
    async def mark_failed(db: AsyncSession, inv_id: str) -> Optional[Payment]:
        try:
            payment = await db.get(Payment, int(inv_id))
        except (TypeError, ValueError):
            return None
        if payment and payment.status == "pending":
            payment.status = "failed"
            await db.commit()
        return payment

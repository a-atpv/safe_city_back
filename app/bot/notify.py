"""Admin Telegram alerts about subscription payments."""
import asyncio
import logging
from typing import Optional, Set

from sqlalchemy import func, select

from app.bot import client
from app.bot.format import escape, money, moment
from app.core import async_session
from app.models import Payment, Subscription, User

logger = logging.getLogger(__name__)

# Strong refs so fire-and-forget tasks are not garbage collected mid-flight.
_tasks: Set[asyncio.Task] = set()


def payment_succeeded(payment_id: int) -> None:
    """Schedule an alert about an activated subscription and return immediately.

    Called from the Robokassa ResultURL path, which has to answer 'OK<InvId>'
    quickly and must never fail just because Telegram is slow or down.
    """
    if not client.is_configured() or not client.admin_chat_ids():
        return
    try:
        task = asyncio.create_task(_notify(payment_id))
    except RuntimeError:  # no running loop (e.g. called from a sync script)
        logger.debug("No event loop for Telegram alert, skipping inv=%s", payment_id)
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _notify(payment_id: int) -> None:
    try:
        async with async_session() as db:
            payment = await db.get(Payment, payment_id)
            if payment is None or payment.status != "success":
                return
            user = await db.get(User, payment.user_id)
            sub = (
                await db.get(Subscription, payment.subscription_id)
                if payment.subscription_id
                else None
            )
            # A user's first successful payment is a new subscriber; anything
            # after it (or any auto-charged child invoice) is a renewal.
            paid_count = (
                await db.execute(
                    select(func.count(Payment.id)).where(
                        Payment.user_id == payment.user_id,
                        Payment.status == "success",
                    )
                )
            ).scalar() or 0
            is_renewal = paid_count > 1 or payment.parent_inv_id is not None
            text = _render(payment, user, sub, is_renewal=is_renewal)
        await client.broadcast_admins(text)
    except Exception:
        logger.exception("Telegram subscription alert failed inv=%s", payment_id)


def _render(
    payment: Payment,
    user: Optional[User],
    sub: Optional[Subscription],
    *,
    is_renewal: bool,
) -> str:
    lines = [
        "🔄 <b>Продление подписки</b>" if is_renewal else "🆕 <b>Новая подписка</b>",
        "",
        f"👤 {escape(user.full_name) if user and user.full_name else 'без имени'}"
        f" — {escape(user.email) if user else '—'}",
        f"🆔 пользователь #{payment.user_id} · счёт #{payment.id}",
        f"📦 {escape(payment.description or payment.plan_type or '—')}",
        f"💰 {money(payment.amount)}",
    ]
    if sub is not None:
        lines.append(f"📅 Действует до {moment(sub.expires_at)}")
        lines.append("🔁 Автопродление: " + ("включено" if sub.auto_renew else "выключено"))
    lines.append(f"🕒 {moment(payment.paid_at)}")
    return "\n".join(lines)

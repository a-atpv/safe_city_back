"""Command handling for incoming Telegram updates.

Only chats listed in TELEGRAM_ADMIN_CHAT_IDS may read statistics. When no admin
is configured yet the bot still answers /start and /id with the caller's chat
id, which is how you bootstrap the config var in the first place.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import client, stats
from app.bot.format import money, moment, number

logger = logging.getLogger(__name__)

HELP = (
    "🤖 <b>Safe City bot</b>\n\n"
    "/stats — статистика по пользователям и подпискам\n"
    "/id — показать id этого чата\n"
    "/help — эта справка\n\n"
    "Уведомления о новых подписках приходят сюда автоматически."
)


PLAN_LABELS = {"monthly": "Месячных", "yearly": "Годовых"}


def _render_stats(data: stats.Stats) -> str:
    plans = (
        "\n".join(
            f"    • {PLAN_LABELS.get(plan, plan)}: {number(count)}"
            for plan, count in sorted(data.subs_by_plan.items())
        )
        or "    • нет активных"
    )
    return (
        "📊 <b>Safe City — статистика</b>\n\n"
        "👥 <b>Пользователи</b>\n"
        f"Всего: <b>{number(data.users_total)}</b>\n"
        f"За 24 часа: +{number(data.users_24h)}\n"
        f"За 7 дней: +{number(data.users_7d)}\n"
        f"За 30 дней: +{number(data.users_30d)}\n\n"
        "💳 <b>Подписки</b>\n"
        f"Активных: <b>{number(data.subs_active)}</b>\n"
        f"{plans}\n"
        f"С автопродлением: {number(data.subs_auto_renew)}\n"
        f"Истекают за 7 дней: {number(data.subs_expiring_7d)}\n\n"
        "💰 <b>Платежи</b>\n"
        f"Всего успешных: {number(data.payments_total)} на {money(data.revenue_total_tiyn)}\n"
        f"За 30 дней: {number(data.payments_30d)} на {money(data.revenue_30d_tiyn)}\n\n"
        f"<i>Обновлено {moment(data.generated_at)}</i>"
    )


async def handle_update(update: dict, db: AsyncSession) -> None:
    """Route one Telegram update. Swallows nothing — the caller logs failures."""
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return

    chat_id = (message.get("chat") or {}).get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text.startswith("/"):
        return

    # Replies must stay inside the forum topic the command came from; outside a
    # forum the field is absent and passing it would make Telegram reject the send.
    thread_id = message.get("message_thread_id") if message.get("is_topic_message") else None

    # "/stats@SafeCityBot arg" -> command "/stats", mention "safecitybot"
    command, _, mention = text.split(maxsplit=1)[0].partition("@")
    command = command.lower()
    if mention:
        # A work group usually holds several bots; ignore their commands.
        username = await client.get_username()
        if username and mention.lower() != username.lower():
            return

    async def reply(body: str) -> None:
        await client.send_message(chat_id, body, thread_id)

    # The chat id to whitelist — with the topic suffix when asked inside a topic.
    config_value = f"{chat_id}:{thread_id}" if thread_id else str(chat_id)

    if command == "/id":
        await reply(f"ID этого чата: <code>{config_value}</code>")
        return

    if chat_id not in client.admin_chat_ids():
        logger.info("Telegram command %s from non-admin chat %s", command, chat_id)
        await reply(
            "🚫 Нет доступа.\n\n"
            f"ID этого чата: <code>{config_value}</code>\n"
            "Добавьте его в переменную <code>TELEGRAM_ADMIN_CHAT_IDS</code> на Heroku."
        )
        return

    if command == "/stats":
        await reply(_render_stats(await stats.collect(db)))
    elif command in ("/start", "/help"):
        await reply(HELP)
    else:
        await reply("Неизвестная команда. /help — список команд.")

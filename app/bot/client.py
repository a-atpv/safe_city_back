"""Minimal Telegram Bot API client.

Deliberately framework-free: the bot only needs sendMessage plus webhook
management, and it shares the web dyno with the API — a full bot framework
would be dead weight in the same process. `httpx` is already a project dep.
"""
import hashlib
import logging
from typing import Any, List, Optional, Tuple

import httpx

from app.core import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
TIMEOUT = httpx.Timeout(10.0)

_username: Optional[str] = None  # cached getMe result


class _RedactToken(logging.Filter):
    """Keep the bot token out of the logs.

    Bot API URLs embed the token in the path and httpx logs every request URL
    at INFO, so without this the token is readable in `heroku logs`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        token = settings.telegram_bot_token
        if token:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    a.replace(token, "***") if isinstance(a, str) else a
                    for a in record.args
                )
            if isinstance(record.msg, str):
                record.msg = record.msg.replace(token, "***")
        return True


logging.getLogger("httpx").addFilter(_RedactToken())


def is_configured() -> bool:
    return bool(settings.telegram_bot_token)


def webhook_secret() -> str:
    """Secret Telegram echoes back in X-Telegram-Bot-Api-Secret-Token.

    Derived from the bot token when not set explicitly, so a working deployment
    needs one config var instead of two.
    """
    if settings.telegram_webhook_secret:
        return settings.telegram_webhook_secret
    return hashlib.sha256((settings.telegram_bot_token or "").encode()).hexdigest()[:32]


def admin_targets() -> List[Tuple[int, Optional[int]]]:
    """(chat_id, thread_id) pairs from TELEGRAM_ADMIN_CHAT_IDS.

    Entries are "-1001234567890" or "-1001234567890:15", where 15 is a forum
    topic id — that is how alerts land in a specific topic of a work group
    instead of General. Group ids are negative; /id prints the right value.
    """
    targets: List[Tuple[int, Optional[int]]] = []
    for part in (settings.telegram_admin_chat_ids or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        chat, _, thread = part.partition(":")
        try:
            targets.append((int(chat), int(thread) if thread.strip() else None))
        except ValueError:
            logger.warning("Ignoring bad TELEGRAM_ADMIN_CHAT_IDS entry: %r", part)
    return targets


def admin_chat_ids() -> List[int]:
    """Chat ids allowed to run commands (thread ids do not gate access)."""
    return [chat_id for chat_id, _ in admin_targets()]


async def _call(method: str, **payload: Any) -> Optional[dict]:
    """POST to the Bot API. Never raises — a dead bot must not break the API."""
    if not is_configured():
        return None
    url = f"{API_BASE}/bot{settings.telegram_bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(url, json=payload)
        data = response.json()
    except Exception as e:
        logger.warning("Telegram %s failed: %s", method, e)
        return None
    if not data.get("ok"):
        logger.warning("Telegram %s rejected: %s", method, data.get("description"))
        return None
    return data.get("result")


async def send_message(
    chat_id: int, text: str, thread_id: Optional[int] = None
) -> bool:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if thread_id is not None:  # forum topics only — sending it elsewhere errors
        payload["message_thread_id"] = thread_id
    return await _call("sendMessage", **payload) is not None


async def broadcast_admins(text: str) -> int:
    """Send to every configured admin chat. Returns how many got through."""
    sent = 0
    for chat_id, thread_id in admin_targets():
        if await send_message(chat_id, text, thread_id):
            sent += 1
    return sent


async def get_username() -> Optional[str]:
    """Bot's @username, fetched once. None if the call fails — callers degrade."""
    global _username
    if _username is None:
        me = await _call("getMe") or {}
        _username = me.get("username")
    return _username


async def set_webhook(url: str) -> bool:
    result = await _call(
        "setWebhook",
        url=url,
        secret_token=webhook_secret(),
        allowed_updates=["message"],
        max_connections=10,
    )
    return result is not None


async def get_webhook_info() -> Optional[dict]:
    return await _call("getWebhookInfo")


async def delete_webhook() -> bool:
    return await _call("deleteWebhook") is not None

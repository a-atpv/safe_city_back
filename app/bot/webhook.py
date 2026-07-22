"""Telegram webhook endpoint.

Runs inside the API's own web dyno — no worker process, no second Heroku app.
Telegram POSTs updates to PUBLIC_BASE_URL + WEBHOOK_PATH; the shared secret
travels in the X-Telegram-Bot-Api-Secret-Token header (set via setWebhook).
"""
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import client
from app.bot.handlers import handle_update
from app.core import get_db, settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["Telegram bot"])

WEBHOOK_PATH = "/api/v1/telegram/webhook"


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    """Receive one update from Telegram.

    Answers 200 even when handling fails: a non-2xx makes Telegram redeliver the
    same update for hours, turning one bug into a request storm on the dyno.
    """
    if not client.is_configured():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not hmac.compare_digest(
        x_telegram_bot_api_secret_token or "", client.webhook_secret()
    ):
        logger.warning("Rejected Telegram webhook call with a bad secret token")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    try:
        await handle_update(update, db)
    except Exception:
        logger.exception("Telegram update handling failed")
    return {"ok": True}


async def setup_webhook() -> None:
    """Point Telegram at this deployment. Runs on startup; idempotent and quiet."""
    if not client.is_configured():
        logger.info("Telegram bot disabled (TELEGRAM_BOT_TOKEN is not set)")
        return
    base = (settings.public_base_url or "").rstrip("/")
    if not base:
        logger.warning(
            "TELEGRAM_BOT_TOKEN is set but PUBLIC_BASE_URL is empty — "
            "webhook not registered, the bot will not receive commands"
        )
        return

    url = f"{base}{WEBHOOK_PATH}"
    info = await client.get_webhook_info()
    if info and info.get("url") == url:
        logger.info("Telegram webhook already registered: %s", url)
        return
    if await client.set_webhook(url):
        logger.info("Telegram webhook registered: %s", url)
    else:
        logger.warning("Could not register Telegram webhook at %s", url)

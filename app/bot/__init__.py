"""Telegram admin bot, served by the API's own web dyno.

Two jobs:
  * `/stats` — user, subscription and payment counters on demand
  * a push alert to the admin chats whenever a subscription is paid for

Wiring: `router` is mounted under /api/v1 (see app/api/__init__.py),
`setup_webhook()` runs on startup (see app/main.py), and the payment flow calls
`notify.payment_succeeded()` (see app/services/payment.py).

Config vars: TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_IDS, PUBLIC_BASE_URL.
Without a token every entry point turns into a no-op, so the API runs unchanged.
"""
from app.bot import client, stats  # noqa: F401  (import order: no app.bot deps)
from app.bot import handlers, notify, webhook  # noqa: F401
from app.bot.webhook import WEBHOOK_PATH, router, schedule_setup, setup_webhook

__all__ = [
    "client",
    "handlers",
    "notify",
    "stats",
    "webhook",
    "router",
    "schedule_setup",
    "setup_webhook",
    "WEBHOOK_PATH",
]

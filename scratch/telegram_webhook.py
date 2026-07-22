"""Inspect or repair the Telegram webhook registration.

    python scratch/telegram_webhook.py          # show current registration
    python scratch/telegram_webhook.py set      # (re)point Telegram at PUBLIC_BASE_URL
    python scratch/telegram_webhook.py delete   # unregister (bot goes silent)

On Heroku: heroku run "python scratch/telegram_webhook.py" -a safe-city-back
The app registers the webhook itself on startup — this is for debugging when
commands do not arrive (look at `last_error_message` in the output).
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bot import client, webhook  # noqa: E402
from app.core import settings  # noqa: E402


async def main() -> None:
    action = (sys.argv[1] if len(sys.argv) > 1 else "info").lower()

    if not client.is_configured():
        print("TELEGRAM_BOT_TOKEN is not set — the bot is disabled.")
        return

    if action == "set":
        await webhook.setup_webhook()
    elif action == "delete":
        print("deleted:", await client.delete_webhook())

    me = await client._call("getMe") or {}
    info = await client.get_webhook_info() or {}
    print(f"bot:            @{me.get('username', '?')}")
    print(f"expected url:   {(settings.public_base_url or '(PUBLIC_BASE_URL unset)').rstrip('/')}"
          f"{webhook.WEBHOOK_PATH}")
    print(f"registered url: {info.get('url') or '(none)'}")
    print(f"admin chats:    {client.admin_chat_ids() or '(none — set TELEGRAM_ADMIN_CHAT_IDS)'}")
    print(f"pending:        {info.get('pending_update_count', 0)}")
    if info.get("last_error_message"):
        print(f"last error:     {info['last_error_message']}")


asyncio.run(main())

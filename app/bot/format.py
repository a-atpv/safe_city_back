"""Shared formatting for bot messages (HTML parse mode)."""
import html
from datetime import datetime, timedelta, timezone
from typing import Optional

# Kazakhstan runs on a single UTC+5 offset since March 2024 — the DB stores UTC,
# the people reading these messages think in Almaty time.
KZ_TZ = timezone(timedelta(hours=5))


def number(value: Optional[int]) -> str:
    """1234567 -> '1 234 567' (non-breaking thin spaces survive Telegram wrapping)."""
    return f"{value or 0:,}".replace(",", " ")


def money(tiyn: Optional[int]) -> str:
    """Payment amounts are stored in tiyn (1 ₸ = 100 tiyn)."""
    return f"{number(round((tiyn or 0) / 100))} ₸"


def moment(value: Optional[datetime]) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KZ_TZ).strftime("%d.%m.%Y %H:%M")


def escape(value: Optional[str]) -> str:
    """Escape user-controlled text — names and emails go into HTML messages."""
    return html.escape(value or "")

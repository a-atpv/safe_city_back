"""
Проверка версии приложения.

Приложение спрашивает при запуске, не устарело ли оно, и показывает баннер
«вышла новая версия». Ответ собирается из переменных окружения, так что
объявить свежую версию можно сразу после её появления в сторе — деплой
бэкенда для этого не нужен.

Эндпоинт публичный: устаревший клиент должен узнать об этом до входа, а не
после — иначе человек упрётся в сломанный логин и решит, что приложение не
работает.
"""

import re
from typing import Literal, Tuple

from fastapi import APIRouter, Query

from app.core.config import settings
from app.schemas.app_update import AppUpdateResponse

router = APIRouter(prefix="/app", tags=["App"])

_VERSION_PART = re.compile(r"\d+")


def _parse(version: str) -> Tuple[int, ...]:
    """'1.0.2+7' → (1, 0, 2). Номер сборки в сравнении не участвует: в сторах
    видна именно строка версии, по ней и объявляется обновление."""
    name = version.split("+", 1)[0]
    parts = [int(p) for p in _VERSION_PART.findall(name)[:3]]
    # Дополняем до трёх компонент: '1.1' и '1.1.0' — одно и то же.
    return tuple(parts + [0] * (3 - len(parts))) if parts else (0, 0, 0)


@router.get("/update", response_model=AppUpdateResponse)
async def check_update(
    version: str = Query(..., description="Версия приложения, например 1.0.2"),
    app: Literal["user", "guard"] = Query("user"),
    platform: Literal["ios", "android"] = Query("android"),
):
    """Нужно ли приложению обновиться."""
    if app == "guard":
        latest = settings.app_guard_latest_version
        minimum = settings.app_guard_min_version
        # Приложение охраны выходит только под Android.
        store_url = settings.app_guard_android_url
    else:
        latest = settings.app_user_latest_version
        minimum = settings.app_user_min_version
        store_url = (
            settings.app_user_ios_url
            if platform == "ios"
            else settings.app_user_android_url
        )

    current = _parse(version)
    update_available = current < _parse(latest)
    update_required = current < _parse(minimum)

    return AppUpdateResponse(
        current_version=version,
        latest_version=latest,
        update_available=update_available,
        update_required=update_required,
        store_url=store_url,
        message=(
            "Установите новую версию, чтобы приложение продолжило работать."
            if update_required
            else ("Вышла новая версия приложения." if update_available else None)
        ),
    )

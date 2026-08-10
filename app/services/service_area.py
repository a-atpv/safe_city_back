"""Гео-ограничение зоны обслуживания.

Экипажи есть только в одном городе, поэтому SOS из другого города обслуживать
некому. Отклоняем такой вызов сразу при создании: иначе человек несколько минут
смотрит на «идёт поиск охраны», который не может ничем закончиться, и всё это
время думает, что помощь едет.

Зона — круг (центр города + радиус), а не полигон городской черты. Это
сознательно: цена ложного отказа (человеку в беде отказали в вызове) намного
выше цены ложного пропуска (приняли вызов из пригорода в паре километров за
чертой), поэтому радиус берём с большим запасом и границу рисуем грубо.

Радиус по умолчанию — 25 км от центра Актобе. Застройка города не уходит от
центра дальше ~10 км (считая аэропорт, Каргалинское водохранилище и посёлки
вокруг), так что запас двукратный; при этом ближайший отдельный город — Алга
(~30 км) — за границу уже не попадает.

Настройки — в переменных окружения (см. Settings.service_area_*). Второй город
добавляется превращением _AREAS в список кругов; менять сам код проверки для
этого не придётся.
"""

from dataclasses import dataclass

from app.core.config import settings
from app.services.routing import _haversine_km


#: Код ошибки в теле ответа. Клиент по нему показывает отдельный экран, а не
#: обычный текст ошибки, поэтому строку менять нельзя — только вместе с
#: приложениями.
OUTSIDE_SERVICE_AREA_CODE = "outside_service_area"


@dataclass(frozen=True)
class ServiceAreaCheck:
    """Результат проверки точки на попадание в зону обслуживания."""

    allowed: bool
    city: str
    distance_km: float
    radius_km: float

    @property
    def message(self) -> str:
        """Текст для пользователя. Всегда даёт запасной путь — 102."""
        return (
            f"Safe City пока работает только в городе {self.city}. "
            "По вашим координатам направить экипаж мы не сможем — "
            "при опасности звоните 102."
        )

    def as_error_detail(self) -> dict:
        """Тело ответа для HTTPException.

        Структурой, а не строкой: `code` нужен приложению, чтобы отличить этот
        случай от прочих ошибок создания вызова, а `message` читают и старые
        клиенты, которые про код ещё не знают.
        """
        return {
            "code": OUTSIDE_SERVICE_AREA_CODE,
            "message": self.message,
            "city": self.city,
        }


def check_service_area(latitude: float, longitude: float) -> ServiceAreaCheck:
    """Проверяет, попадает ли точка в зону обслуживания.

    При выключенной проверке (SERVICE_AREA_ENABLED=false) всегда разрешает —
    это рубильник на случай, если гео-ограничение начнёт мешать реальным
    вызовам, и способ гонять тестовые вызовы из другого города.
    """
    distance_km = _haversine_km(
        latitude,
        longitude,
        settings.service_area_lat,
        settings.service_area_lng,
    )
    return ServiceAreaCheck(
        allowed=(not settings.service_area_enabled)
        or distance_km <= settings.service_area_radius_km,
        city=settings.service_area_city,
        distance_km=distance_km,
        radius_km=settings.service_area_radius_km,
    )

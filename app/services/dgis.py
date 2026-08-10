"""
2GIS (2ГИС) services: routing + geocoding.

Это часть перехода SafeCity с OSM-стека на 2ГИС: картография 2ГИС заметно
точнее в Казахстане (дома, подъезды, дворовые проезды), а инструкции
маршрута приходят сразу на русском.

Ключ выдаётся на dev.2gis.com и задаётся переменной окружения DGIS_API_KEY
(один ключ на Routing API и Geocoder API). Пока ключа нет или 2ГИС
недоступен, вызывающий код (RoutingService / OpenStreetMapService) сам
откатывается на прежний стек OSRM + Nominatim, поэтому включение 2ГИС —
это просто появление ключа в окружении.

Docs:
  Routing:  https://docs.2gis.com/ru/api/navigation/routing/overview
  Geocoder: https://docs.2gis.com/ru/api/search/geocoder/overview
"""

import logging
import math
import re
from collections import Counter
from typing import List, Optional, Tuple

import httpx
import polyline as polyline_lib

from app.core.config import settings
from app.services.geo import distance_to_geometry_m
from app.services.geocoding import GeocodingResult
from app.services.routing import RouteResult, RouteStep, _haversine_km

logger = logging.getLogger(__name__)

# Каждый запрос к 2ГИС — списанная единица тарифа, и узнать остаток можно только
# в кабинете постфактум: в ответе его нет (в заголовках приходит лишь
# x-apikey-status). Поэтому расход считаем сами и пишем в лог — иначе квота
# кончается внезапно, как это и произошло на демо-ключе.
#
#   heroku logs -a <app> -n 1500 | grep -c '\[2gis-quota\] routing'
#
# Счётчик живёт в памяти процесса и обнуляется при рестарте дино; для «сколько
# сожгли за сессию тестов» этого достаточно, за месяц считайте по строкам лога.
_billed: Counter = Counter()


def _bill(unit: str) -> None:
    """Отметить в логе списанную единицу тарифа 2ГИС."""
    _billed[unit] += 1
    logger.info(f"[2gis-quota] {unit} #{_billed[unit]} (с рестарта процесса)")


def _format_distance(meters: float) -> str:
    """Format meters into human-readable string (Russian)."""
    if meters < 1000:
        return f"{int(meters)} м"
    return f"{meters / 1000:.1f} км"


# Пары "lon lat" внутри WKT LINESTRING(82.93 55.01, 82.94 55.02, ...)
_WKT_PAIR_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)")

# Фразы на случай, когда 2ГИС не прислал comment для манёвра.
_TURN_PHRASES = {
    "straight": "Продолжайте движение прямо",
    "left": "Поверните налево",
    "slightly_left": "Держитесь левее",
    "sharply_left": "Резко налево",
    "right": "Поверните направо",
    "slightly_right": "Держитесь правее",
    "sharply_right": "Резко направо",
    "u_turn": "Развернитесь",
}

# Краевые манёвры: и в comment, и в type приходят служебные маркеры.
_TYPE_PHRASES = {
    "start": "Начало движения",
    "begin": "Начало движения",
    "end": "Вы прибыли",
    "finish": "Вы прибыли",
}


def _parse_wkt_selection(selection: str) -> List[Tuple[float, float]]:
    """WKT 'LINESTRING(lon lat, lon lat, ...)' → [(lat, lng), ...]."""
    return [
        (float(lat), float(lon))
        for lon, lat in _WKT_PAIR_RE.findall(selection)
    ]


class DGisRoutingService:
    """
    Автомобильные маршруты через 2GIS Routing API (routing/7.0.0/global).

    Возвращает RouteResult в том же формате, что и OSRM-путь в
    RoutingService, поэтому приложение охранника ничего не замечает —
    меняется только качество маршрута и язык инструкций.
    """

    ROUTING_URL = "https://routing.api.2gis.com/routing/7.0.0/global"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.dgis_api_key)

    @classmethod
    async def get_route(
        cls,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        with_steps: bool = False,
    ) -> RouteResult:
        """Построить маршрут. Бросает исключение при любой проблеме —
        вызывающий код откатывается на OSRM."""

        body = {
            "points": [
                {"type": "stop", "lon": origin_lng, "lat": origin_lat},
                {"type": "stop", "lon": dest_lng, "lat": dest_lat},
            ],
            "transport": "driving",
            "locale": "ru",
            "route_mode": "fastest",
            # Учитывать пробки: ETA охранника должно быть честным.
            "traffic_mode": "jam",
            # Полная геометрия участков (WKT) — из неё собираем polyline.
            "output": "detailed",
        }

        _bill("routing")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                cls.ROUTING_URL,
                params={"key": settings.dgis_api_key},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        routes = data.get("result") or []
        if not routes:
            raise ValueError(f"2GIS routing returned no routes: {data.get('message') or data.get('type', 'empty result')}")

        route = routes[0]

        # Склеиваем геометрию всех манёвров в один список точек [lat, lng].
        coords: List[Tuple[float, float]] = []
        steps: List[RouteStep] = []
        for maneuver in route.get("maneuvers") or []:
            path = maneuver.get("outcoming_path") or {}
            for segment in path.get("geometry") or []:
                for pt in _parse_wkt_selection(segment.get("selection", "")):
                    if not coords or coords[-1] != pt:
                        coords.append(pt)

            if with_steps:
                # У краевых манёвров comment — служебный маркер "start"/
                # "finish", а не текст для человека (проверено на живом API).
                raw = (maneuver.get("comment") or "").strip()
                instruction = "" if raw.lower() in _TYPE_PHRASES else raw
                if not instruction:
                    instruction = (
                        _TYPE_PHRASES.get(raw.lower())
                        or _TYPE_PHRASES.get(maneuver.get("type", ""))
                        or _TURN_PHRASES.get(maneuver.get("turn_direction", ""))
                        or maneuver.get("type", "")
                    )
                if instruction or path:
                    street_names = [n for n in (path.get("names") or []) if n]
                    steps.append(RouteStep(
                        instruction=instruction,
                        distance_meters=float(path.get("distance") or 0),
                        duration_seconds=float(path.get("duration") or 0),
                        # Улица, по которой едем после манёвра.
                        name=", ".join(street_names),
                    ))

        if len(coords) < 2:
            raise ValueError("2GIS routing returned no usable geometry")

        distance_m = float(route.get("total_distance") or 0)
        duration_sec = float(route.get("total_duration") or 0)
        if distance_m <= 0:
            raise ValueError("2GIS routing returned zero distance")

        eta_minutes = max(1, int(duration_sec / 60 + 0.5))

        return RouteResult(
            # Google polyline precision 5 — тот же формат, что у OSRM.
            geometry=polyline_lib.encode(coords),
            coordinates=[[lat, lng] for lat, lng in coords],
            distance_meters=distance_m,
            duration_seconds=duration_sec,
            eta_minutes=eta_minutes,
            distance_text=_format_distance(distance_m),
            steps=steps,
        )


class DGisGeocodingService:
    """
    Геокодинг через 2GIS Geocoder API (catalog.api.2gis.com).

    Возвращает GeocodingResult — тот же dataclass, что и у Nominatim,
    поэтому форматирование адресов в EmergencyService не меняется.
    """

    GEOCODE_URL = "https://catalog.api.2gis.com/3.0/items/geocode"
    _FIELDS = "items.point,items.address,items.adm_div,items.full_name"

    # Для обратного геокодинга дополнительно просим контуры зданий: по ним
    # видно, в какой дом точка попала и до какого ближе. Прямому геокодингу
    # контуры не нужны, поэтому список полей отдельный.
    _REVERSE_FIELDS = f"{_FIELDS},items.geometry.hover"

    # Короче, чем у Nominatim-фолбэка: приложение ждёт весь ответ бэкенда
    # не дольше 10 с, и в этот бюджет должны уложиться оба провайдера.
    _TIMEOUT = 6.0

    # В каком радиусе искать дом или улицу при обратном геокодинге. С фильтром
    # `type` радиус обязателен — без него 2ГИС отдаёт пустой список. 200 м: в
    # застройке ближайший дом находится и в пятидесяти, а запас нужен для
    # промзон и новых районов, где до ближайшего адреса дальше.
    _REVERSE_RADIUS_M = 200

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.dgis_api_key)

    @staticmethod
    def _locale(language: str) -> str:
        # Продукт работает в Казахстане: ru → ru_KZ, kk → kk_KZ.
        return f"{language}_KZ"

    @classmethod
    def _parse_item(cls, item: dict, fallback_lat: float, fallback_lon: float) -> GeocodingResult:
        point = item.get("point") or {}
        adm_div = item.get("adm_div") or []

        def _adm(kind: str) -> Optional[str]:
            for div in adm_div:
                if div.get("type") == kind and div.get("name"):
                    return div["name"]
            return None

        road: Optional[str] = None
        house_number: Optional[str] = None
        components = (item.get("address") or {}).get("components") or []
        for comp in components:
            if comp.get("type") == "street_number":
                road = comp.get("street") or road
                house_number = comp.get("number") or house_number
                break
        if road is None and item.get("type") == "street":
            road = item.get("name")

        return GeocodingResult(
            latitude=float(point.get("lat", fallback_lat)),
            longitude=float(point.get("lon", fallback_lon)),
            display_name=item.get("full_name") or item.get("address_name") or item.get("name") or "",
            city=_adm("city") or _adm("settlement"),
            country=_adm("country"),
            road=road,
            house_number=house_number,
        )

    @staticmethod
    def _has_street_address(item: dict) -> bool:
        """Есть ли у объекта улица с номером дома.

        Дом без них подписью быть не может: 2ГИС возвращает такие как
        «Сооружение» или «Объект», и во дворе они нередко оказываются ближе
        всех к точке.
        """
        components = (item.get("address") or {}).get("components") or []
        return any(
            comp.get("type") == "street_number" and comp.get("street")
            for comp in components
        )

    @staticmethod
    def _distance_m(item: dict, latitude: float, longitude: float) -> float:
        """Метры до объекта: по контуру, если 2ГИС его дал, иначе по центроиду.

        Разница существенная: у длинной свечки центроид может быть в 60 м, а
        стена — в пяти, и по центроидам «ближайшим» оказывается соседний дом.
        """
        distance = distance_to_geometry_m(
            latitude, longitude, (item.get("geometry") or {}).get("hover")
        )
        if distance is not None:
            return distance
        point = item.get("point") or {}
        if "lat" in point and "lon" in point:
            return _haversine_km(latitude, longitude, point["lat"], point["lon"]) * 1000
        return math.inf

    @classmethod
    def _pick_reverse_item(
        cls,
        items: List[dict],
        latitude: float,
        longitude: float,
    ) -> Optional[dict]:
        """Выбирает из ответа 2ГИС объект, который и есть адрес точки.

        Нельзя брать items[0]: 2ГИС сортирует выдачу по релевантности, а не по
        расстоянию. Во дворе Братьев Жубановых он ставил первым дом 289, хотя
        289в там ближе на семь метров, а 289а — дальше на два: охранник видел
        адрес соседнего дома и не мог понять, почему. Поэтому расстояние
        считаем сами, по контурам, и дом, в чей контур точка попала, побеждает
        любой другой (у него расстояние 0).

        Улица — вариант последней очереди: «улица Братьев Жубановых» без номера
        полезнее, чем ничего, но хуже любого дома с номером.

        Граница возможностей: 2ГИС отдаёт не больше 10 объектов на запрос
        (page_size > 10 у этого эндпоинта возвращает пустую выдачу), а в
        плотной застройке в радиусе 200 м их пятьдесят с лишним. Выбираем из
        того десятка, что 2ГИС счёл релевантным; на проверенных точках квартала
        дом, в контур которого попадала точка, в этот десяток попадал всегда.
        """
        candidates: List[Tuple[int, float, dict]] = []
        for item in items:
            if item.get("type") == "street":
                tier = 1
            elif cls._has_street_address(item):
                tier = 0
            else:
                continue
            candidates.append((tier, cls._distance_m(item, latitude, longitude), item))

        if not candidates:
            return None
        tier, distance, item = min(candidates, key=lambda c: (c[0], c[1]))
        logger.debug(
            "[DGisGeocoding] reverse %.6f,%.6f → %r (%.0f м, из %d вариантов)",
            latitude,
            longitude,
            item.get("full_name"),
            distance,
            len(candidates),
        )
        return item

    @classmethod
    async def _reverse_items(
        cls,
        latitude: float,
        longitude: float,
        language: str,
        extra: Optional[dict] = None,
    ) -> List[dict]:
        """Один запрос к геокодеру. Пустой список — и когда 2ГИС ответил
        ошибкой, и когда рядом ничего не нашлось; вызывающий решает, что
        делать дальше."""
        _bill("geocoder reverse")
        async with httpx.AsyncClient(timeout=cls._TIMEOUT) as client:
            resp = await client.get(
                cls.GEOCODE_URL,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "fields": cls._REVERSE_FIELDS,
                    "locale": cls._locale(language),
                    "key": settings.dgis_api_key,
                    **(extra or {}),
                },
            )
            # «Ничего не нашлось» 2ГИС отдаёт кодом 404 — и в теле (meta.code),
            # и, при желании, в статусе. Это не ошибка и не повод ругаться в лог.
            if resp.status_code == 404:
                return []
            if resp.status_code != 200:
                logger.warning(f"[DGisGeocoding] reverse HTTP {resp.status_code}")
                return []
            data = resp.json()

        return (data.get("result") or {}).get("items") or []

    @classmethod
    async def reverse_geocode(
        cls,
        latitude: float,
        longitude: float,
        language: str = "ru",
    ) -> Optional[GeocodingResult]:
        """Координаты → адрес. Возвращает None при любой проблеме —
        вызывающий код откатывается на Nominatim.

        Сначала спрашиваем дом или улицу в радиусе и выбираем из выдачи сами
        (см. [_pick_reverse_item]), и только если рядом ничего нет — что угодно.
        Без фильтра 2ГИС охотно отвечает районом: во дворе Братьев Жубановых 289
        он выдавал «Актобе, Астана» (название микрорайона), и охранник с
        диспетчером видели название района вместо адреса. Точку вызова это не
        двигает — координаты SOS берутся от телефона, из ответа геокодера
        читается только подпись.
        """
        try:
            near = await cls._reverse_items(
                latitude,
                longitude,
                language,
                {"type": "building,street", "radius": cls._REVERSE_RADIUS_M},
            )
            best = cls._pick_reverse_item(near, latitude, longitude)
            if best is not None:
                return cls._parse_item(best, latitude, longitude)

            # Ни дома, ни улицы рядом (степь, трасса) — пусть будет хотя бы
            # населённый пункт с районом. Здесь выдача — административные
            # единицы без контуров, выбирать среди них по расстоянию нечем,
            # поэтому берём первую: 2ГИС ставит вперёд самую мелкую.
            any_items = await cls._reverse_items(latitude, longitude, language)
            if not any_items:
                return None
            return cls._parse_item(any_items[0], latitude, longitude)
        except Exception as e:
            # repr: сетевые исключения httpx стрингифицируются в пустоту.
            logger.warning(f"[DGisGeocoding] reverse geocoding error: {e!r}")
            return None

    @classmethod
    async def geocode(
        cls,
        query: str,
        language: str = "ru",
        limit: int = 5,
    ) -> list[GeocodingResult]:
        """Адрес → координаты. Пустой список при любой проблеме."""
        try:
            _bill("geocoder forward")
            async with httpx.AsyncClient(timeout=cls._TIMEOUT) as client:
                resp = await client.get(
                    cls.GEOCODE_URL,
                    params={
                        "q": query,
                        "fields": cls._FIELDS,
                        "page_size": limit,
                        "locale": cls._locale(language),
                        "key": settings.dgis_api_key,
                    },
                )
                if resp.status_code != 200:
                    logger.warning(f"[DGisGeocoding] geocode HTTP {resp.status_code}")
                    return []
                data = resp.json()

            items = (data.get("result") or {}).get("items") or []
            return [
                cls._parse_item(item, 0.0, 0.0)
                for item in items
                if item.get("point")
            ]
        except Exception as e:
            logger.warning(f"[DGisGeocoding] geocoding error: {e!r}")
            return []

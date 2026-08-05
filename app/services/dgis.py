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

import re
from typing import List, Optional, Tuple

import httpx
import polyline as polyline_lib

from app.core.config import settings
from app.services.geocoding import GeocodingResult
from app.services.routing import RouteResult, RouteStep


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
                instruction = (maneuver.get("comment") or "").strip()
                if not instruction:
                    instruction = _TURN_PHRASES.get(
                        maneuver.get("turn_direction", ""),
                        maneuver.get("type", ""),
                    )
                if instruction or path:
                    steps.append(RouteStep(
                        instruction=instruction,
                        distance_meters=float(path.get("distance") or 0),
                        duration_seconds=float(path.get("duration") or 0),
                        # 2ГИС не отдаёт название улицы отдельным полем —
                        # оно уже внутри текста инструкции.
                        name="",
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

    @classmethod
    async def reverse_geocode(
        cls,
        latitude: float,
        longitude: float,
        language: str = "ru",
    ) -> Optional[GeocodingResult]:
        """Координаты → адрес. Возвращает None при любой проблеме —
        вызывающий код откатывается на Nominatim."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    cls.GEOCODE_URL,
                    params={
                        "lat": latitude,
                        "lon": longitude,
                        "fields": cls._FIELDS,
                        "locale": cls._locale(language),
                        "key": settings.dgis_api_key,
                    },
                )
                if resp.status_code != 200:
                    print(f"[DGisGeocoding] reverse HTTP {resp.status_code}")
                    return None
                data = resp.json()

            items = (data.get("result") or {}).get("items") or []
            if not items:
                return None
            return cls._parse_item(items[0], latitude, longitude)
        except Exception as e:
            print(f"[DGisGeocoding] reverse geocoding error: {e}")
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
                    print(f"[DGisGeocoding] geocode HTTP {resp.status_code}")
                    return []
                data = resp.json()

            items = (data.get("result") or {}).get("items") or []
            return [
                cls._parse_item(item, 0.0, 0.0)
                for item in items
                if item.get("point")
            ]
        except Exception as e:
            print(f"[DGisGeocoding] geocoding error: {e}")
            return []

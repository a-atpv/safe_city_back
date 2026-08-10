"""Плоская геометрия для выбора дома по координате.

2ГИС отдаёт контуры зданий в WKT (поле `items.geometry.hover`), а обратному
геокодингу нужно ответить на два вопроса: попала ли точка внутрь дома и, если
нет, до какого дома ближе. Полноценная геобиблиотека для этого не нужна —
расстояния здесь десятки метров, поэтому переводим градусы в метры локальной
проекцией и считаем на плоскости. Погрешность такой проекции в масштабе
квартала — доли процента, зато в образ не тянется GEOS/shapely.

Считаем в системе с началом координат в самой точке: тогда «внутри контура»
превращается в «начало координат внутри многоугольника», а расстояние — в
«длина кратчайшего вектора до его рёбер». Это заметно короче, чем общий случай.

WKT у 2ГИС записан в порядке «долгота широта».
"""

import math
import re
from typing import List, Optional, Tuple

#: Метров в градусе широты. Для долготы домножается на косинус широты.
_M_PER_DEG_LAT = 111_320.0

#: Внутренние скобочные группы WKT: «lon lat, lon lat, ...». Регулярное
#: выражение намеренно не умеет вложенных скобок — благодаря этому каждая
#: найденная группа это ровно одно кольцо POLYGON, один контур MULTIPOLYGON,
#: одна линия MULTILINESTRING или одинокий POINT, и разбирать тип геометрии
#: отдельно не требуется.
_WKT_GROUP_RE = re.compile(r"\(([-\d.,eE+\s]+)\)")

Point = Tuple[float, float]


def _coord_groups(wkt: str) -> List[List[Point]]:
    """Разбирает WKT в списки точек (долгота, широта)."""
    groups: List[List[Point]] = []
    for raw in _WKT_GROUP_RE.findall(wkt):
        points: List[Point] = []
        for pair in raw.split(","):
            parts = pair.split()
            if len(parts) < 2:
                continue
            try:
                points.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
        if points:
            groups.append(points)
    return groups


def _to_local_xy(lon: float, lat: float, lon0: float, lat0: float) -> Point:
    """Градусы → метры относительно точки (lon0, lat0)."""
    return (
        (lon - lon0) * _M_PER_DEG_LAT * math.cos(math.radians(lat0)),
        (lat - lat0) * _M_PER_DEG_LAT,
    )


def _origin_to_segment_m(a: Point, b: Point) -> float:
    """Расстояние от начала координат до отрезка ab."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(ax, ay)
    # Параметр проекции начала координат на прямую ab, зажатый в пределы отрезка.
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
    return math.hypot(ax + t * dx, ay + t * dy)


def _ring_contains_origin(ring: List[Point]) -> bool:
    """Лежит ли начало координат внутри замкнутого контура.

    Обычный подсчёт пересечений: пускаем луч вдоль +X и считаем рёбра, которые
    он пересёк. Нечётное число — точка внутри.
    """
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > 0) == (y2 > 0):
            continue  # ребро целиком выше или ниже луча
        if x1 + (0.0 - y1) * (x2 - x1) / (y2 - y1) > 0:
            inside = not inside
    return inside


def distance_to_geometry_m(lat: float, lon: float, wkt: Optional[str]) -> Optional[float]:
    """Метры от точки до геометрии; 0.0 — точка внутри контура.

    None — геометрии нет или её не удалось разобрать; вызывающий код тогда
    считает расстояние по центроиду.

    Отверстия POLYGON проверяются наравне с внешним кольцом: точка во дворе
    П-образного дома — всё равно адрес этого дома, а не соседнего.
    """
    if not wkt:
        return None
    groups = _coord_groups(wkt)
    if not groups:
        return None

    best: Optional[float] = None
    for group in groups:
        ring = [_to_local_xy(g_lon, g_lat, lon, lat) for g_lon, g_lat in group]
        # Замкнутый контур (у 2ГИС последняя точка повторяет первую) — сначала
        # проверяем попадание внутрь. У незамкнутых линий улиц смысла в этом нет.
        if len(ring) >= 4 and ring[0] == ring[-1] and _ring_contains_origin(ring):
            return 0.0
        if len(ring) == 1:
            distance = math.hypot(*ring[0])
        else:
            distance = min(
                _origin_to_segment_m(ring[i], ring[i + 1])
                for i in range(len(ring) - 1)
            )
        best = distance if best is None else min(best, distance)
    return best

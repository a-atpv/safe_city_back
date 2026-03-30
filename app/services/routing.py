"""
Routing service using OSRM (Open Source Routing Machine).
Uses the free public demo server. For production, deploy your own OSRM instance.
Docs: https://router.project-osrm.org/
"""

import httpx
import polyline as polyline_lib
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from math import radians, cos, sin, asin, sqrt


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RouteStep:
    """A single navigation instruction."""
    instruction: str
    distance_meters: float
    duration_seconds: float
    name: str  # road / street name


@dataclass
class RouteResult:
    """Full route between two points."""
    # Encoded polyline (Google Polyline Algorithm, precision 5)
    geometry: str
    # Decoded list of [lat, lng] for convenience
    coordinates: List[List[float]]
    # Total distance in meters
    distance_meters: float
    # Total duration in seconds
    duration_seconds: float
    # Human-friendly ETA
    eta_minutes: int
    # Human-friendly distance
    distance_text: str
    # Turn-by-turn steps (optional, only if requested)
    steps: List[RouteStep] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Haversine helper — straight-line distance (used as fallback)
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points on earth (km)."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def _format_distance(meters: float) -> str:
    """Format meters into human-readable string (Russian)."""
    if meters < 1000:
        return f"{int(meters)} м"
    return f"{meters / 1000:.1f} км"


# ---------------------------------------------------------------------------
# OSRM Routing Service
# ---------------------------------------------------------------------------

class RoutingService:
    """
    Routing service powered by OSRM.

    Uses the public demo server by default.
    For production, set OSRM_BASE_URL to your self-hosted instance:
        docker run -t -v osrm-data:/data osrm/osrm-backend osrm-routed ...
    """

    # Public demo server — rate-limited, suitable for development & testing
    OSRM_BASE_URL = "https://router.project-osrm.org"
    USER_AGENT = "SafeCity/1.0 (support@safecity.kz)"

    # Fallback average city speed (km/h) when OSRM is unavailable
    FALLBACK_SPEED_KMH = 40

    @classmethod
    async def get_route(
        cls,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        with_steps: bool = False,
        alternatives: bool = False,
    ) -> Optional[RouteResult]:
        """
        Get driving route between two points.

        Args:
            origin_lat/lng: Guard's current position
            dest_lat/lng:   Emergency call (user) position
            with_steps:     Include turn-by-turn navigation
            alternatives:   Include alternative routes

        Returns:
            RouteResult or None on failure
        """
        try:
            return await cls._osrm_route(
                origin_lat, origin_lng,
                dest_lat, dest_lng,
                with_steps=with_steps,
                alternatives=alternatives,
            )
        except Exception as e:
            print(f"[RoutingService] OSRM failed, using fallback: {e}")
            return cls._fallback_route(
                origin_lat, origin_lng,
                dest_lat, dest_lng,
            )

    @classmethod
    async def get_eta_minutes(
        cls,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> int:
        """Quick ETA-only call (lightweight)."""
        route = await cls.get_route(origin_lat, origin_lng, dest_lat, dest_lng)
        if route:
            return route.eta_minutes
        # Worst-case fallback
        dist_km = _haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
        return max(1, int((dist_km / cls.FALLBACK_SPEED_KMH) * 60))

    # ------------------------------------------------------------------
    # OSRM implementation
    # ------------------------------------------------------------------

    @classmethod
    async def _osrm_route(
        cls,
        o_lat: float, o_lng: float,
        d_lat: float, d_lng: float,
        with_steps: bool = False,
        alternatives: bool = False,
    ) -> RouteResult:
        """Call OSRM route API and parse the response."""

        # OSRM uses lng,lat order (GeoJSON convention)
        coords = f"{o_lng},{o_lat};{d_lng},{d_lat}"
        url = f"{cls.OSRM_BASE_URL}/route/v1/driving/{coords}"

        params = {
            "overview": "full",           # full polyline geometry
            "geometries": "polyline",     # Google encoded polyline
            "steps": str(with_steps).lower(),
            "alternatives": str(alternatives).lower(),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                url,
                params=params,
                headers={"User-Agent": cls.USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            raise ValueError(f"OSRM returned: {data.get('code', 'unknown')}")

        route = data["routes"][0]
        geometry_encoded = route["geometry"]
        duration_sec = route["duration"]    # seconds
        distance_m = route["distance"]      # meters

        # Decode polyline to list of [lat, lng]
        decoded = polyline_lib.decode(geometry_encoded)
        coordinates = [[lat, lng] for lat, lng in decoded]

        # Parse steps if requested
        steps = []
        if with_steps and route.get("legs"):
            for leg in route["legs"]:
                for s in leg.get("steps", []):
                    maneuver = s.get("maneuver", {})
                    instruction = maneuver.get("type", "")
                    modifier = maneuver.get("modifier", "")
                    if modifier:
                        instruction = f"{instruction} {modifier}"

                    steps.append(RouteStep(
                        instruction=instruction,
                        distance_meters=s.get("distance", 0),
                        duration_seconds=s.get("duration", 0),
                        name=s.get("name", ""),
                    ))

        eta_minutes = max(1, int(duration_sec / 60 + 0.5))

        return RouteResult(
            geometry=geometry_encoded,
            coordinates=coordinates,
            distance_meters=distance_m,
            duration_seconds=duration_sec,
            eta_minutes=eta_minutes,
            distance_text=_format_distance(distance_m),
            steps=steps,
        )

    # ------------------------------------------------------------------
    # Fallback (straight-line estimation)
    # ------------------------------------------------------------------

    @classmethod
    def _fallback_route(
        cls,
        o_lat: float, o_lng: float,
        d_lat: float, d_lng: float,
    ) -> RouteResult:
        """Straight-line fallback when OSRM is down."""
        dist_km = _haversine_km(o_lat, o_lng, d_lat, d_lng)
        # Multiply by 1.3 to approximate road distance
        road_dist_km = dist_km * 1.3
        road_dist_m = road_dist_km * 1000
        eta_hours = road_dist_km / cls.FALLBACK_SPEED_KMH
        eta_seconds = eta_hours * 3600
        eta_minutes = max(1, int(eta_seconds / 60 + 0.5))

        # Create a simple two-point "polyline"
        encoded = polyline_lib.encode([(o_lat, o_lng), (d_lat, d_lng)])

        return RouteResult(
            geometry=encoded,
            coordinates=[[o_lat, o_lng], [d_lat, d_lng]],
            distance_meters=road_dist_m,
            duration_seconds=eta_seconds,
            eta_minutes=eta_minutes,
            distance_text=_format_distance(road_dist_m),
            steps=[],
        )

    # ------------------------------------------------------------------
    # Multi-point route (future: multiple stops)
    # ------------------------------------------------------------------

    @classmethod
    async def get_route_multi(
        cls,
        waypoints: List[Tuple[float, float]],
        with_steps: bool = False,
    ) -> Optional[RouteResult]:
        """
        Get route through multiple waypoints.
        waypoints: list of (lat, lng) tuples, minimum 2.
        """
        if len(waypoints) < 2:
            return None

        try:
            coords = ";".join(f"{lng},{lat}" for lat, lng in waypoints)
            url = f"{cls.OSRM_BASE_URL}/route/v1/driving/{coords}"

            params = {
                "overview": "full",
                "geometries": "polyline",
                "steps": str(with_steps).lower(),
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    url,
                    params=params,
                    headers={"User-Agent": cls.USER_AGENT},
                )
                resp.raise_for_status()
                data = resp.json()

            if data.get("code") != "Ok" or not data.get("routes"):
                return None

            route = data["routes"][0]
            geometry_encoded = route["geometry"]
            decoded = polyline_lib.decode(geometry_encoded)
            coordinates = [[lat, lng] for lat, lng in decoded]

            return RouteResult(
                geometry=geometry_encoded,
                coordinates=coordinates,
                distance_meters=route["distance"],
                duration_seconds=route["duration"],
                eta_minutes=max(1, int(route["duration"] / 60 + 0.5)),
                distance_text=_format_distance(route["distance"]),
                steps=[],
            )
        except Exception as e:
            print(f"[RoutingService] Multi-point route failed: {e}")
            return None

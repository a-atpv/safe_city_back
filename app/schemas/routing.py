"""Schemas for routing / navigation endpoints."""

from pydantic import BaseModel, Field
from typing import Optional, List


class RouteRequest(BaseModel):
    """Request body for getting a route."""
    origin_lat: float = Field(..., ge=-90, le=90, description="Origin latitude (guard position)")
    origin_lng: float = Field(..., ge=-180, le=180, description="Origin longitude (guard position)")
    dest_lat: float = Field(..., ge=-90, le=90, description="Destination latitude (user/call position)")
    dest_lng: float = Field(..., ge=-180, le=180, description="Destination longitude (user/call position)")
    with_steps: bool = Field(False, description="Include turn-by-turn navigation steps")


class RouteStepResponse(BaseModel):
    """Single turn-by-turn navigation step."""
    instruction: str
    distance_meters: float
    duration_seconds: float
    name: str


class RouteResponse(BaseModel):
    """Full route response — maps directly to the map polyline UI."""
    # Encoded polyline string (Google Polyline Algorithm, precision 5)
    # Use this directly with flutter_polyline_points or google_maps_flutter
    geometry: str

    # Decoded coordinates [[lat, lng], ...] — alternative to geometry
    coordinates: List[List[float]]

    # Metrics
    distance_meters: float
    duration_seconds: float
    eta_minutes: int
    distance_text: str

    # Optional turn-by-turn
    steps: List[RouteStepResponse] = []


class CallRouteResponse(BaseModel):
    """
    Route + call context. Used by the guard app's active call screen.
    Maps to the UI screenshot: guard location → user location, blue polyline, "~4 мин" badge.
    """
    call_id: int
    call_status: str

    # User (victim) location
    user_latitude: float
    user_longitude: float
    user_address: Optional[str] = None

    # Guard location (current)
    guard_latitude: Optional[float] = None
    guard_longitude: Optional[float] = None

    # Route
    route: Optional[RouteResponse] = None

    # Guard brief info
    guard_name: Optional[str] = None
    guard_avatar_url: Optional[str] = None
    guard_rating: Optional[float] = None
    guard_total_reviews: Optional[int] = None
    guard_phone: Optional[str] = None


class ETAResponse(BaseModel):
    """Lightweight ETA-only response."""
    eta_minutes: int
    distance_text: str

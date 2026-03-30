"""
Routing / Navigation endpoints for the Guard App.

Provides:
  - Route from guard → emergency call location (polyline + ETA)
  - Standalone point-to-point routing
  - Quick ETA lookup

These power the Guard App's "active call" map screen with:
  • Blue polyline overlay
  • "~4 мин" ETA badge
  • Guard-to-user distance
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db
from app.api.deps import get_current_guard
from app.models import Guard, CallStatus
from app.schemas.routing import (
    RouteRequest,
    RouteResponse,
    RouteStepResponse,
    CallRouteResponse,
    ETAResponse,
)
from app.schemas.common import APIResponse
from app.services.routing import RoutingService
from app.services.emergency import EmergencyService

router = APIRouter(prefix="/guard/route", tags=["Guard Navigation"])


# ============ Call-specific route ============

@router.get("/call/{call_id}", response_model=CallRouteResponse)
async def get_route_to_call(
    call_id: int,
    with_steps: bool = Query(False, description="Include turn-by-turn steps"),
    current_guard: Guard = Depends(get_current_guard),
    db: AsyncSession = Depends(get_db),
):
    """
    Get route from guard's current location to the emergency call location.

    This is the primary endpoint for the guard's active call screen.
    It returns everything needed to render:
      - Map polyline (blue route)
      - ETA badge ("~4 мин")
      - Guard & user info
      - User's address
    """
    call = await EmergencyService.get_by_id(db, call_id)
    if not call or call.guard_id != current_guard.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Call not found"
        )

    # Guard must have a known location
    if not current_guard.current_latitude or not current_guard.current_longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Guard location unknown. Send location update first."
        )

    # Build route
    route_result = await RoutingService.get_route(
        origin_lat=current_guard.current_latitude,
        origin_lng=current_guard.current_longitude,
        dest_lat=call.latitude,
        dest_lng=call.longitude,
        with_steps=with_steps,
    )

    route = None
    if route_result:
        route = RouteResponse(
            geometry=route_result.geometry,
            coordinates=route_result.coordinates,
            distance_meters=route_result.distance_meters,
            duration_seconds=route_result.duration_seconds,
            eta_minutes=route_result.eta_minutes,
            distance_text=route_result.distance_text,
            steps=[
                RouteStepResponse(
                    instruction=s.instruction,
                    distance_meters=s.distance_meters,
                    duration_seconds=s.duration_seconds,
                    name=s.name,
                ) for s in route_result.steps
            ],
        )

        # Also update the call's ETA field
        call.estimated_arrival_minutes = route_result.eta_minutes
        await db.flush()

    return CallRouteResponse(
        call_id=call.id,
        call_status=call.status.value if hasattr(call.status, 'value') else str(call.status),
        user_latitude=call.latitude,
        user_longitude=call.longitude,
        user_address=call.address,
        guard_latitude=current_guard.current_latitude,
        guard_longitude=current_guard.current_longitude,
        route=route,
        guard_name=current_guard.full_name,
        guard_avatar_url=current_guard.avatar_url,
        guard_rating=current_guard.rating,
        guard_total_reviews=current_guard.total_reviews,
        guard_phone=current_guard.phone,
    )


# ============ Standalone point-to-point route ============

@router.post("/calculate", response_model=RouteResponse)
async def calculate_route(
    data: RouteRequest,
    current_guard: Guard = Depends(get_current_guard),
):
    """
    Calculate a route between any two points.
    Useful for previewing routes before accepting a call.
    """
    route_result = await RoutingService.get_route(
        origin_lat=data.origin_lat,
        origin_lng=data.origin_lng,
        dest_lat=data.dest_lat,
        dest_lng=data.dest_lng,
        with_steps=data.with_steps,
    )

    if not route_result:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Routing service unavailable"
        )

    return RouteResponse(
        geometry=route_result.geometry,
        coordinates=route_result.coordinates,
        distance_meters=route_result.distance_meters,
        duration_seconds=route_result.duration_seconds,
        eta_minutes=route_result.eta_minutes,
        distance_text=route_result.distance_text,
        steps=[
            RouteStepResponse(
                instruction=s.instruction,
                distance_meters=s.distance_meters,
                duration_seconds=s.duration_seconds,
                name=s.name,
            ) for s in route_result.steps
        ],
    )


# ============ Quick ETA ============

@router.get("/eta", response_model=ETAResponse)
async def get_eta(
    dest_lat: float = Query(..., ge=-90, le=90),
    dest_lng: float = Query(..., ge=-180, le=180),
    current_guard: Guard = Depends(get_current_guard),
):
    """
    Quick ETA from guard's current location to a destination.
    Lightweight — returns only ETA and distance, no polyline.
    """
    if not current_guard.current_latitude or not current_guard.current_longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Guard location unknown"
        )

    route = await RoutingService.get_route(
        origin_lat=current_guard.current_latitude,
        origin_lng=current_guard.current_longitude,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
    )

    if not route:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Routing service unavailable"
        )

    return ETAResponse(
        eta_minutes=route.eta_minutes,
        distance_text=route.distance_text,
    )

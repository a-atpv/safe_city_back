"""
Geocoding endpoints for the Guard App.

Раньше приложение охранника ходило в Nominatim напрямую с устройства.
С переходом на 2ГИС адреса выдаёт бэкенд: единое качество (2ГИС с
фолбэком на Nominatim), а ключ 2ГИС не покидает сервер.
"""

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_guard
from app.models import Guard
from app.schemas.geocode import ReverseGeocodeResponse
from app.services.dgis import DGisGeocodingService
from app.services.geocoding import OpenStreetMapService

router = APIRouter(prefix="/guard/geocode", tags=["Guard Geocoding"])


@router.get("/reverse", response_model=ReverseGeocodeResponse)
async def reverse_geocode(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    current_guard: Guard = Depends(get_current_guard),
):
    """Координаты → адрес. Сначала 2ГИС, при неудаче — Nominatim."""
    result = None
    if DGisGeocodingService.is_configured():
        result = await DGisGeocodingService.reverse_geocode(lat, lon)
    if result is None:
        result = await OpenStreetMapService.reverse_geocode(lat, lon)

    if result is None:
        return ReverseGeocodeResponse(found=False)

    # Короткая подпись в том же виде, в каком её раньше собирало приложение:
    # «улица номер», иначе первые две части полного адреса.
    short = None
    if result.road:
        short = result.road
        if result.house_number:
            short += f" {result.house_number}"
    elif result.display_name:
        short = ", ".join(p.strip() for p in result.display_name.split(",")[:2])

    return ReverseGeocodeResponse(
        found=True,
        address=short,
        full_address=result.display_name or None,
        city=result.city,
        road=result.road,
        house_number=result.house_number,
    )

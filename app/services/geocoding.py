import httpx
from typing import Optional
from dataclasses import dataclass


@dataclass
class GeocodingResult:
    """Result of a geocoding or reverse geocoding query"""
    latitude: float
    longitude: float
    display_name: str
    city: Optional[str] = None
    country: Optional[str] = None
    road: Optional[str] = None
    house_number: Optional[str] = None


class OpenStreetMapService:
    """
    Geocoding service using OpenStreetMap Nominatim API.
    Free, no API key required. Respects usage policy with User-Agent.
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org"
    USER_AGENT = "SafeCity/1.0 (support@safecity.kz)"

    @classmethod
    async def reverse_geocode(
        cls,
        latitude: float,
        longitude: float,
        language: str = "ru"
    ) -> Optional[GeocodingResult]:
        """Convert coordinates to address (reverse geocoding)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{cls.NOMINATIM_URL}/reverse",
                    params={
                        "lat": latitude,
                        "lon": longitude,
                        "format": "json",
                        "addressdetails": 1,
                        "accept-language": language,
                    },
                    headers={"User-Agent": cls.USER_AGENT}
                )
                if response.status_code != 200:
                    return None

                data = response.json()
                address = data.get("address", {})

                return GeocodingResult(
                    latitude=float(data.get("lat", latitude)),
                    longitude=float(data.get("lon", longitude)),
                    display_name=data.get("display_name", ""),
                    city=address.get("city") or address.get("town") or address.get("village"),
                    country=address.get("country"),
                    road=address.get("road"),
                    house_number=address.get("house_number"),
                )
        except Exception as e:
            print(f"Reverse geocoding error: {e}")
            return None

    @classmethod
    async def geocode(
        cls,
        query: str,
        language: str = "ru",
        limit: int = 5,
        country_codes: str = "kz"
    ) -> list[GeocodingResult]:
        """Convert address to coordinates (forward geocoding)"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{cls.NOMINATIM_URL}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "addressdetails": 1,
                        "limit": limit,
                        "countrycodes": country_codes,
                        "accept-language": language,
                    },
                    headers={"User-Agent": cls.USER_AGENT}
                )
                if response.status_code != 200:
                    return []

                results = []
                for item in response.json():
                    address = item.get("address", {})
                    results.append(GeocodingResult(
                        latitude=float(item["lat"]),
                        longitude=float(item["lon"]),
                        display_name=item.get("display_name", ""),
                        city=address.get("city") or address.get("town") or address.get("village"),
                        country=address.get("country"),
                        road=address.get("road"),
                        house_number=address.get("house_number"),
                    ))
                return results
        except Exception as e:
            print(f"Geocoding error: {e}")
            return []

    @classmethod
    async def get_address_for_call(
        cls,
        latitude: float,
        longitude: float,
        language: str = "ru"
    ) -> str:
        """Get a human-readable address for an emergency call location"""
        result = await cls.reverse_geocode(latitude, longitude, language)
        if not result:
            return f"{latitude:.6f}, {longitude:.6f}"

        # Build short address
        parts = []
        if result.road:
            parts.append(result.road)
        if result.house_number:
            parts.append(result.house_number)
        if result.city:
            parts.append(result.city)

        if parts:
            return ", ".join(parts)
        return result.display_name or f"{latitude:.6f}, {longitude:.6f}"

    @classmethod
    def get_tile_url(cls) -> str:
        """Return OSM tile URL for map rendering on clients"""
        return "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    @classmethod
    def get_tile_attribution(cls) -> str:
        """Return required OSM attribution string"""
        return "© OpenStreetMap contributors"

from typing import Optional
from pydantic import BaseModel


class ReverseGeocodeResponse(BaseModel):
    """Адрес по координатам для приложения охранника."""
    found: bool
    # Короткая подпись для карты: «Абая 150»
    address: Optional[str] = None
    full_address: Optional[str] = None
    city: Optional[str] = None
    road: Optional[str] = None
    house_number: Optional[str] = None

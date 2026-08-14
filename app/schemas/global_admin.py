"""Schemas for the platform-level (global admin) API.

Kept apart from schemas/admin.py: those describe what a company sees about
itself, these describe what the platform owner sees across all companies —
colours, per-company counters and the map overview.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


def hex_color_field():
    """A colour is either empty or #RRGGBB — the map draws it straight into CSS.

    A function rather than a shared Field() instance: pydantic binds FieldInfo to
    the model it is declared in, so one instance must not be reused across models.
    """
    return Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


# ============ Companies ============

class GlobalCompanyResponse(BaseModel):
    id: int
    name: str
    legal_name: Optional[str] = None
    logo_url: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    license_number: Optional[str] = None

    map_color: Optional[str] = None
    service_latitude: Optional[float] = None
    service_longitude: Optional[float] = None
    service_radius_km: Optional[float] = None

    is_active: bool
    is_accepting_calls: bool
    priority: int

    # Counters the platform list needs; filled by the service, not by the ORM.
    guards_total: int = 0
    guards_online: int = 0
    admins_total: int = 0

    total_calls: int = 0
    completed_calls: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class GlobalCompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    legal_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    license_number: Optional[str] = None

    map_color: Optional[str] = hex_color_field()
    service_latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    service_longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    service_radius_km: Optional[float] = Field(default=None, gt=0, le=500)

    is_accepting_calls: bool = True
    priority: int = 0

    # The company's first admin. Optional, but without it nobody can sign in to
    # the company panel and "войти как компания" has no account to borrow.
    owner_email: Optional[EmailStr] = None
    owner_password: Optional[str] = Field(default=None, min_length=6)
    owner_full_name: Optional[str] = None


class GlobalCompanyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    legal_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    license_number: Optional[str] = None

    map_color: Optional[str] = hex_color_field()
    service_latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    service_longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    service_radius_km: Optional[float] = Field(default=None, gt=0, le=500)

    is_active: Optional[bool] = None
    is_accepting_calls: Optional[bool] = None
    priority: Optional[int] = None


class GlobalCompanyOwner(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    role: str

    class Config:
        from_attributes = True


class GlobalCompanyCreated(BaseModel):
    company: GlobalCompanyResponse
    owner: Optional[GlobalCompanyOwner] = None


# ============ Map ============

class GlobalMapCompany(BaseModel):
    id: int
    name: str
    map_color: Optional[str] = None
    service_latitude: Optional[float] = None
    service_longitude: Optional[float] = None
    service_radius_km: Optional[float] = None
    is_active: bool
    is_accepting_calls: bool
    guards_total: int = 0
    guards_online: int = 0


class GlobalMapGuard(BaseModel):
    """A ГБР unit as it is drawn on the platform map."""
    id: int
    company_id: int
    full_name: str
    phone: Optional[str] = None
    status: str
    is_online: bool
    is_on_call: bool
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    last_location_update: Optional[datetime] = None


class GlobalMapResponse(BaseModel):
    companies: List[GlobalMapCompany]
    guards: List[GlobalMapGuard]

from typing import Optional
from pydantic import BaseModel, ConfigDict


class DeviceRegister(BaseModel):
    """Schema for registering or updating a device token for push notifications."""
    device_token: str
    device_type: str  # android, ios, web
    device_model: Optional[str] = None
    app_version: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DeviceResponse(DeviceRegister):
    """Schema for device response."""
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

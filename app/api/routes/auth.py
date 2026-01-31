from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db, create_access_token, create_refresh_token, decode_token
from app.schemas import (
    PhoneRequest, 
    VerifyOTPRequest, 
    TokenResponse, 
    RefreshTokenRequest,
    APIResponse
)
from app.services import send_otp_to_phone, OTPService, UserService
from app.core.config import settings
from datetime import timedelta
import phonenumbers

router = APIRouter(prefix="/auth", tags=["Authentication"])


def normalize_phone(phone: str) -> str:
    """Normalize phone number to E164 format"""
    try:
        parsed = phonenumbers.parse(phone, "KZ")
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Invalid phone number")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format"
        )


@router.post("/request-otp", response_model=APIResponse)
async def request_otp(data: PhoneRequest):
    """Request OTP code for phone number"""
    phone = normalize_phone(data.phone)
    
    success, debug_otp = await send_otp_to_phone(phone)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP"
        )
    
    response_data = {"phone": phone}
    if settings.debug and debug_otp:
        response_data["otp"] = debug_otp  # Only in debug mode!
    
    return APIResponse(
        success=True,
        message="OTP sent successfully",
        data=response_data
    )


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp(
    data: VerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify OTP and return tokens"""
    phone = normalize_phone(data.phone)
    
    is_valid = await OTPService.verify_otp(phone, data.code)
    
    if not is_valid:
        remaining = await OTPService.get_remaining_attempts(phone)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP code. Attempts remaining: {remaining}"
        )
    
    # Get or create user
    user = await UserService.get_by_phone(db, phone)
    if not user:
        user = await UserService.create(db, phone)
    
    # Generate tokens
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token"""
    payload = decode_token(data.refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = payload.get("sub")
    user = await UserService.get_by_id(db, int(user_id))
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    # Generate new tokens
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60
    )

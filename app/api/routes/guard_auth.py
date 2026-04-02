import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import get_db, create_access_token, create_refresh_token, decode_token
from app.schemas.guard import GuardEmailRequest, GuardVerifyOTPRequest, GuardTokenResponse, GuardRefreshTokenRequest
from app.schemas.common import APIResponse
from app.services.email import OTPService, send_otp_to_email
from app.services.guard import GuardService
from app.core.config import settings
from datetime import timedelta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guard/auth", tags=["Guard Authentication"])


@router.post("/request-otp", response_model=APIResponse)
async def request_otp(
    data: GuardEmailRequest,
    db: AsyncSession = Depends(get_db)
):
    """Request OTP code for guard email address"""
    email = data.email.strip().lower()

    # Verify guard exists in the system (registered by company admin)
    guard = await GuardService.get_by_email(db, email)
    if not guard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Guard not found. Please contact your company admin."
        )

    if guard.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guard account is not active"
        )

    success, debug_otp = await send_otp_to_email(email)

    if not success and not settings.debug:
        logger.error(f"Failed to send OTP to {email}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP. Please check your email configuration."
        )

    response_data = {"email": email}
    if debug_otp:
        response_data["otp"] = debug_otp

    return APIResponse(
        success=success, # might be False if debug and email failed
        message="OTP sent successfully" if success else "OTP generated (Email delivery failed - Debug mode)",
        data=response_data
    )


@router.post("/verify-otp", response_model=GuardTokenResponse)
async def verify_otp(
    data: GuardVerifyOTPRequest,
    db: AsyncSession = Depends(get_db)
):
    """Verify OTP and return tokens for guard"""
    email = data.email.strip().lower()

    is_valid = await OTPService.verify_otp(email, data.code)
    if not is_valid:
        remaining = await OTPService.get_remaining_attempts(email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP code. Attempts remaining: {remaining}"
        )

    guard = await GuardService.get_by_email(db, email)
    if not guard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Guard not found"
        )

    # Generate tokens with guard role
    access_token = create_access_token(
        data={"sub": str(guard.id), "role": "guard"},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    refresh_token = create_refresh_token(
        data={"sub": str(guard.id), "role": "guard"}
    )

    return GuardTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        role="guard"
    )


@router.post("/refresh", response_model=GuardTokenResponse)
async def refresh_token(
    data: GuardRefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh guard access token"""
    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh" or payload.get("role") != "guard":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    guard_id = payload.get("sub")
    guard = await GuardService.get_by_id(db, int(guard_id))

    if not guard:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guard not found"
        )

    access_token = create_access_token(
        data={"sub": str(guard.id), "role": "guard"},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes)
    )
    new_refresh_token = create_refresh_token(
        data={"sub": str(guard.id), "role": "guard"}
    )

    return GuardTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        role="guard"
    )

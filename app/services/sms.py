import random
import httpx
from typing import Optional
from app.core.config import settings
from app.core.redis import get_redis


class OTPService:
    """Service for OTP generation, storage and verification"""
    
    OTP_PREFIX = "otp:"
    OTP_ATTEMPTS_PREFIX = "otp_attempts:"
    MAX_ATTEMPTS = 3
    
    @staticmethod
    def generate_otp() -> str:
        """Generate random OTP code"""
        return ''.join([str(random.randint(0, 9)) for _ in range(settings.otp_length)])
    
    @classmethod
    async def store_otp(cls, phone: str, otp: str) -> None:
        """Store OTP in Redis with expiration"""
        redis = get_redis()
        key = f"{cls.OTP_PREFIX}{phone}"
        await redis.setex(key, settings.otp_expire_minutes * 60, otp)
        # Reset attempts
        attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{phone}"
        await redis.delete(attempts_key)
    
    @classmethod
    async def verify_otp(cls, phone: str, otp: str) -> bool:
        """Verify OTP code"""
        redis = get_redis()
        key = f"{cls.OTP_PREFIX}{phone}"
        attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{phone}"
        
        # Check attempts
        attempts = await redis.get(attempts_key)
        if attempts and int(attempts) >= cls.MAX_ATTEMPTS:
            return False
        
        stored_otp = await redis.get(key)
        if stored_otp and stored_otp == otp:
            # Delete OTP after successful verification
            await redis.delete(key)
            await redis.delete(attempts_key)
            return True
        
        # Increment attempts
        await redis.incr(attempts_key)
        await redis.expire(attempts_key, settings.otp_expire_minutes * 60)
        return False
    
    @classmethod
    async def get_remaining_attempts(cls, phone: str) -> int:
        """Get remaining OTP attempts"""
        redis = get_redis()
        attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{phone}"
        attempts = await redis.get(attempts_key)
        if attempts:
            return max(0, cls.MAX_ATTEMPTS - int(attempts))
        return cls.MAX_ATTEMPTS


class SMSService:
    """Service for sending SMS via Brevo"""
    
    BREVO_API_URL = "https://api.brevo.com/v3/transactionalSMS/sms"
    
    @classmethod
    async def send_otp(cls, phone: str, otp: str) -> bool:
        """Send OTP via SMS"""
        if not settings.brevo_api_key:
            # Development mode - just log
            print(f"[DEV] SMS to {phone}: Your Safe City code: {otp}")
            return True
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    cls.BREVO_API_URL,
                    headers={
                        "api-key": settings.brevo_api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "type": "transactional",
                        "unicodeEnabled": True,
                        "sender": "SafeCity",
                        "recipient": phone,
                        "content": f"Ваш код для Safe City: {otp}. Не сообщайте его никому.",
                    }
                )
                return response.status_code == 201
        except Exception as e:
            print(f"SMS sending error: {e}")
            return False


async def send_otp_to_phone(phone: str) -> tuple[bool, Optional[str]]:
    """Generate, store and send OTP to phone"""
    otp = OTPService.generate_otp()
    await OTPService.store_otp(phone, otp)
    
    success = await SMSService.send_otp(phone, otp)
    
    if settings.debug:
        # Return OTP in debug mode for testing
        return success, otp
    return success, None

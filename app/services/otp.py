import logging
import random
from typing import Optional
from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class OTPService:
    """Unified service for OTP generation, storage and verification"""
    
    OTP_PREFIX = "otp:"
    OTP_ATTEMPTS_PREFIX = "otp_attempts:"
    MAX_ATTEMPTS = 5 # Increased from 3 to 5 for better UX
    
    @staticmethod
    def generate_otp() -> str:
        """Generate random OTP code of configured length"""
        return ''.join([str(random.randint(0, 9)) for _ in range(settings.otp_length)])
    
    @classmethod
    async def store_otp(cls, identifier: str, otp: str) -> bool:
        """
        Store OTP in Redis with expiration.
        Identifier can be an email or a phone number.
        """
        try:
            redis = get_redis()
            if not redis:
                logger.error("OTPService: Redis client is not initialized")
                return False

            # Ensure lowercase for consistency (especially for emails)
            key_id = identifier.strip().lower()
            key = f"{cls.OTP_PREFIX}{key_id}"
            
            # Store with expiration
            await redis.setex(key, settings.otp_expire_minutes * 60, otp)
            
            # Reset attempts when a new OTP is stored
            attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{key_id}"
            await redis.delete(attempts_key)
            
            logger.info(f"OTPService: Stored new OTP for {key_id}")
            return True
        except Exception as e:
            logger.error(f"OTPService: Error storing OTP for {identifier}: {e}")
            return False
    
    @classmethod
    async def verify_otp(cls, identifier: str, otp: str) -> bool:
        """
        Verify OTP code.
        Returns True if valid, False otherwise.
        """
        try:
            redis = get_redis()
            if not redis:
                logger.error("OTPService: Redis client is not initialized")
                return False

            key_id = identifier.strip().lower()
            key = f"{cls.OTP_PREFIX}{key_id}"
            attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{key_id}"
            
            # 1. Clean up input OTP (strip whitespace)
            clean_otp = otp.strip()
            
            # 2. Check attempts limit first
            attempts = await redis.get(attempts_key)
            if attempts and int(attempts) >= cls.MAX_ATTEMPTS:
                logger.warning(f"OTPService: Max attempts reached for {key_id}")
                return False
            
            # 3. Retrieve stored OTP
            stored_otp = await redis.get(key)
            
            if not stored_otp:
                logger.warning(f"OTPService: No OTP found in Redis for {key_id} (expired or never stored)")
                # We still increment attempts to prevent exhaustive searching if the key doesn't exist?
                # Actually, if it's not even there, just incrementing attempts_key to track flakiness.
                await redis.incr(attempts_key)
                await redis.expire(attempts_key, settings.otp_expire_minutes * 60)
                return False
            
            # 4. Compare
            if stored_otp == clean_otp:
                # Success! Delete OTP and attempts
                await redis.delete(key)
                await redis.delete(attempts_key)
                logger.info(f"OTPService: Successful verification for {key_id}")
                return True
            
            # 5. Mismatch - increment attempts
            new_attempts = await redis.incr(attempts_key)
            await redis.expire(attempts_key, settings.otp_expire_minutes * 60)
            
            logger.warning(f"OTPService: Invalid OTP attempt {new_attempts}/{cls.MAX_ATTEMPTS} for {key_id}")
            return False
            
        except Exception as e:
            logger.error(f"OTPService: Exception during verification for {identifier}: {e}")
            return False
    
    @classmethod
    async def get_remaining_attempts(cls, identifier: str) -> int:
        """Get remaining OTP attempts for an identifier"""
        try:
            redis = get_redis()
            if not redis:
                return cls.MAX_ATTEMPTS
                
            key_id = identifier.strip().lower()
            attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{key_id}"
            attempts = await redis.get(attempts_key)
            
            if attempts:
                return max(0, cls.MAX_ATTEMPTS - int(attempts))
            return cls.MAX_ATTEMPTS
        except Exception:
            return cls.MAX_ATTEMPTS

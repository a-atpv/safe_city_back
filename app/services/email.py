import logging
import random
import httpx
from typing import Optional
from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


from app.services.otp import OTPService


class EmailService:
    """Service for sending emails via Brevo REST API"""
    
    BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
    
    @classmethod
    async def send_otp(cls, email: str, otp: str) -> bool:
        """Send OTP via Email using Brevo REST API"""
        if not settings.brevo_api_key:
            # Development mode - just log
            print(f"[DEV] Email to {email}: Your Safe City code: {otp}")
            return True
        
        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #e2e8f0; padding: 40px;">
                <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 16px; padding: 40px; border: 1px solid #334155;">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <span style="font-size: 32px;">🛡️</span>
                        <h1 style="color: #f1f5f9; margin-top: 20px; font-size: 24px;">Safe City</h1>
                    </div>
                    <p style="color: #94a3b8; font-size: 16px; text-align: center;">Ваш код подтверждения:</p>
                    <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0;">
                        <span style="font-size: 36px; font-weight: bold; color: white; letter-spacing: 8px;">{otp}</span>
                    </div>
                    <p style="color: #64748b; font-size: 14px; text-align: center;">Код действителен {settings.otp_expire_minutes} минут.</p>
                </div>
            </body>
            </html>
            """
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    cls.BREVO_API_URL,
                    headers={
                        "api-key": settings.brevo_api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "sender": {"email": "alekseigradoboev553@gmail.com", "name": "Safe City"},
                        "to": [{"email": email}],
                        "subject": f"Код подтверждения Safe City: {otp}",
                        "htmlContent": html_content
                    }
                )
                if response.status_code not in (200, 201, 202):
                    logger.error(f"Brevo email error {response.status_code}: {response.text}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Email sending exception: {e}")
            return False


async def send_otp_to_email(email: str) -> tuple[bool, Optional[str]]:
    """Generate, store and send OTP to email"""
    otp = OTPService.generate_otp()
    await OTPService.store_otp(email, otp)
    
    success = await EmailService.send_otp(email, otp)
    
    if settings.debug:
        # Return OTP in debug mode for testing
        return success, otp
    return success, None

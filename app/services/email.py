import random
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
    async def store_otp(cls, email: str, otp: str) -> None:
        """Store OTP in Redis with expiration"""
        redis = get_redis()
        key = f"{cls.OTP_PREFIX}{email.lower()}"
        await redis.setex(key, settings.otp_expire_minutes * 60, otp)
        # Reset attempts
        attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{email.lower()}"
        await redis.delete(attempts_key)
    
    @classmethod
    async def verify_otp(cls, email: str, otp: str) -> bool:
        """Verify OTP code"""
        redis = get_redis()
        key = f"{cls.OTP_PREFIX}{email.lower()}"
        attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{email.lower()}"
        
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
    async def get_remaining_attempts(cls, email: str) -> int:
        """Get remaining OTP attempts"""
        redis = get_redis()
        attempts_key = f"{cls.OTP_ATTEMPTS_PREFIX}{email.lower()}"
        attempts = await redis.get(attempts_key)
        if attempts:
            return max(0, cls.MAX_ATTEMPTS - int(attempts))
        return cls.MAX_ATTEMPTS


class EmailService:
    """Service for sending emails via SMTP (Brevo)"""
    
    @classmethod
    def send_otp(cls, email: str, otp: str) -> bool:
        """Send OTP via Email"""
        if not settings.smtp_user or not settings.smtp_password:
            # Development mode - just log
            print(f"[DEV] Email to {email}: Your Safe City code: {otp}")
            return True
        
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = f"Код подтверждения Safe City: {otp}"
            message["From"] = settings.from_email
            message["To"] = email
            
            # Plain text version
            text = f"""
Ваш код для Safe City: {otp}

Код действителен {settings.otp_expire_minutes} минут.
Не сообщайте этот код никому.

С уважением,
Команда Safe City
            """
            
            # HTML version
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #e2e8f0; padding: 40px;">
    <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border-radius: 16px; padding: 40px; border: 1px solid #334155;">
        <div style="text-align: center; margin-bottom: 30px;">
            <div style="display: inline-block; background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 16px; border-radius: 12px;">
                <span style="font-size: 32px;">🛡️</span>
            </div>
            <h1 style="color: #f1f5f9; margin-top: 20px; font-size: 24px;">Safe City</h1>
        </div>
        
        <p style="color: #94a3b8; font-size: 16px; text-align: center;">Ваш код подтверждения:</p>
        
        <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0;">
            <span style="font-size: 36px; font-weight: bold; color: white; letter-spacing: 8px;">{otp}</span>
        </div>
        
        <p style="color: #64748b; font-size: 14px; text-align: center;">
            Код действителен {settings.otp_expire_minutes} минут.<br>
            Не сообщайте этот код никому.
        </p>
        
        <hr style="border: none; border-top: 1px solid #334155; margin: 30px 0;">
        
        <p style="color: #475569; font-size: 12px; text-align: center;">
            Если вы не запрашивали этот код, проигнорируйте это письмо.
        </p>
    </div>
</body>
</html>
            """
            
            part1 = MIMEText(text, "plain")
            part2 = MIMEText(html, "html")
            message.attach(part1)
            message.attach(part2)
            
            # Send email
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls(context=context)
                server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.from_email, email, message.as_string())
            
            return True
        except Exception as e:
            print(f"Email sending error: {e}")
            return False


async def send_otp_to_email(email: str) -> tuple[bool, Optional[str]]:
    """Generate, store and send OTP to email"""
    otp = OTPService.generate_otp()
    await OTPService.store_otp(email, otp)
    
    success = EmailService.send_otp(email, otp)
    
    if settings.debug:
        # Return OTP in debug mode for testing
        return success, otp
    return success, None

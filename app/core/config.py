from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://safecity:safecity_secret_2024@localhost:5432/safecity"

    @model_validator(mode="after")
    def fix_database_url(self):
        """Convert Heroku's postgres:// to postgresql+asyncpg:// for async SQLAlchemy."""
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # JWT
    jwt_secret: str = "your-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # 90 days, not a week: the SOS app is opened rarely by design, and a refresh
    # token that dies of old age means an e-mail OTP round trip before the one
    # screen the user came for.
    refresh_token_expire_days: int = 90
    
    # SMTP / Brevo API
    brevo_api_key: Optional[str] = None
    smtp_host: str = "smtp-relay.brevo.com"
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: str = "alekseigradoboev553@gmail.com"
    
    # App
    env: str = "development"
    debug: bool = True
    
    # OTP
    otp_expire_minutes: int = 5
    otp_length: int = 4
    
    # Bootstrap
    bootstrap_admin_email: Optional[str] = None
    bootstrap_admin_password: Optional[str] = None
    bootstrap_global_admin_email: Optional[str] = None
    bootstrap_global_admin_password: Optional[str] = None
    
    # Firebase
    firebase_credentials_path: str = "Safe City Firebase Admin SDK.json"
    firebase_credentials_json: Optional[str] = None
    # iOS critical alerts make the SOS siren ignore the mute switch and Do Not
    # Disturb, but they require the com.apple.developer.usernotifications
    # .critical-alerts entitlement, which Apple grants per-app on request.
    # Leave off until that entitlement is on the guard app's provisioning
    # profile — sending a critical sound without it makes APNS drop the push.
    fcm_ios_critical_alerts: bool = False
    
    # 2GIS / 2ГИС (dev.2gis.com) — один ключ на Routing API и Geocoder API.
    # Пока ключ не задан, маршруты строит OSRM, адреса ищет Nominatim (переход
    # на 2ГИС включается самим фактом появления ключа, см. app/services/dgis.py).
    dgis_api_key: Optional[str] = None

    # Версии приложений для баннера «вышло обновление». Задаются переменными
    # окружения, поэтому объявить новую версию можно сразу после выкладки в
    # стор — без релиза бэкенда и уж точно без релиза приложений.
    #   latest — что лежит в сторе: приложение старее покажет предложение
    #            обновиться, которое можно отложить;
    #   min    — ниже этой версии работать нельзя: диалог без кнопки «Позже».
    # min поднимать только тогда, когда старый клиент действительно сломан
    # (несовместимый API): он запирает человека в диалоге, а для приложения с
    # тревожной кнопкой это отказ в помощи.
    app_user_latest_version: str = "1.0.2"
    app_user_min_version: str = "0.0.0"
    app_guard_latest_version: str = "1.0.1"
    app_guard_min_version: str = "0.0.0"
    app_user_ios_url: str = "https://apps.apple.com/kz/app/id6759368857"
    app_user_android_url: str = (
        "https://play.google.com/store/apps/details?id=com.safeCity.appname"
    )
    app_guard_android_url: str = (
        "https://play.google.com/store/apps/details?id=com.safeCityGuard.appname"
    )

    # AWS S3
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "eu-north-1"
    aws_bucket_name: str = "safe-sity"
    
    # Robokassa (Kazakhstan) — https://docs.robokassa.kz/
    robokassa_merchant_login: Optional[str] = None
    robokassa_password1: Optional[str] = None
    robokassa_password2: Optional[str] = None
    robokassa_is_test: bool = True
    robokassa_hash_algo: str = "sha256"  # md5 | sha1 | sha256 | sha384 | sha512 — MUST match the shop cabinet
    robokassa_payment_url: str = "https://auth.robokassa.kz/Merchant/Index.aspx"
    robokassa_recurring_url: str = "https://auth.robokassa.kz/Merchant/Recurring"
    robokassa_vat: str = "none"  # KZ receipt tax tag: none | vat0 | vat5 | vat12 | vat16
    # Where to redirect the user after payment (frontend WEB pages). If set, the
    # Success/Fail callbacks 302 here. If unset, an HTML page bounces the user
    # back into the mobile app via the custom scheme below.
    payment_success_redirect: Optional[str] = None
    payment_fail_redirect: Optional[str] = None
    # Custom URL scheme of the mobile app, used to return from the payment
    # browser back into the app (deep link "<scheme>://pay/success|fail").
    payment_app_scheme: str = "safecity"

    # Public HTTPS origin of this deployment, e.g. https://safe-city-back.herokuapp.com
    # Used to register the Telegram webhook on startup.
    public_base_url: Optional[str] = None

    # Telegram admin bot (served by this same web dyno, no extra process)
    telegram_bot_token: Optional[str] = None
    # Comma-separated chat ids allowed to run commands + receiving subscription
    # alerts. Send /id to the bot to learn a chat's id.
    telegram_admin_chat_ids: Optional[str] = None
    # Optional override; defaults to a value derived from the bot token.
    telegram_webhook_secret: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

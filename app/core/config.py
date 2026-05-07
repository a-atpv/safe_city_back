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
    refresh_token_expire_days: int = 7
    
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
    
    # AWS S3
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "eu-north-1"
    aws_bucket_name: str = "safe-sity"
    
    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

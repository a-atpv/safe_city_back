import redis.asyncio as redis
from app.core.config import settings
import ssl

redis_client: redis.Redis = None

# Connection pool settings for Heroku Redis stability
_REDIS_COMMON_KWARGS = dict(
    decode_responses=True,
    retry_on_timeout=True,
    socket_keepalive=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    health_check_interval=30,
)


async def init_redis():
    global redis_client
    # Heroku Redis uses rediss:// (TLS) which requires ssl configuration
    if settings.redis_url.startswith("rediss://"):
        redis_client = redis.from_url(
            settings.redis_url,
            ssl_cert_reqs="none",
            **_REDIS_COMMON_KWARGS,
        )
    else:
        redis_client = redis.from_url(settings.redis_url, **_REDIS_COMMON_KWARGS)


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()


def get_redis() -> redis.Redis:
    return redis_client

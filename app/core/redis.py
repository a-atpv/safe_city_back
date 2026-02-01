import redis.asyncio as redis
from app.core.config import settings
import ssl

redis_client: redis.Redis = None


async def init_redis():
    global redis_client
    # Heroku Redis uses rediss:// (TLS) which requires ssl configuration
    if settings.redis_url.startswith("rediss://"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        redis_client = redis.from_url(
            settings.redis_url, 
            decode_responses=True,
            ssl=ssl_context
        )
    else:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()


def get_redis() -> redis.Redis:
    return redis_client

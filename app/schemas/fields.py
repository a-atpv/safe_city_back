from typing import Annotated, Optional
from pydantic import PlainSerializer


def _presign_avatar(value: Optional[str]) -> Optional[str]:
    """Serialize a stored S3 avatar URL into a time-limited presigned URL."""
    # Imported lazily to avoid a circular import at module load time
    # (app.services package -> user service -> app.schemas).
    from app.services.s3 import s3_service
    return s3_service.presign_url(value)


# Use for any response field that holds an S3 avatar/photo URL. On serialization
# the stored public URL is converted into a presigned GET URL so private bucket
# objects are viewable by clients.
AvatarUrl = Annotated[
    Optional[str],
    PlainSerializer(_presign_avatar, return_type=Optional[str], when_used="json"),
]

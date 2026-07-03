import uuid
import logging
from typing import Optional
from fastapi import UploadFile, HTTPException
import boto3
from botocore.exceptions import ClientError
from app.core.config import settings

logger = logging.getLogger(__name__)

# Allowed image content types
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


class S3Service:
    """Service for uploading and deleting files in AWS S3"""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )
        return self._client

    @property
    def bucket(self) -> str:
        return settings.aws_bucket_name

    def _build_url(self, key: str) -> str:
        """Build the public URL for an S3 object."""
        return f"https://{self.bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"

    def _key_from_url(self, url: str) -> Optional[str]:
        """Extract the S3 object key from a full URL."""
        prefix = f"https://{self.bucket}.s3.{settings.aws_region}.amazonaws.com/"
        if url.startswith(prefix):
            return url[len(prefix):]
        return None

    def presign_url(self, url: Optional[str], expires_in: int = 604800) -> Optional[str]:
        """
        Convert a stored public S3 URL into a time-limited presigned GET URL so
        that private bucket objects can be fetched by clients without public ACLs.

        Returns the original value unchanged if it is empty, not one of our S3
        objects, or if signing fails (e.g. missing credentials in dev).
        """
        if not url:
            return url

        # Already a presigned URL (has query params) — leave as-is.
        if "?" in url:
            return url

        key = self._key_from_url(url)
        if key is None:
            return url

        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except Exception as e:  # noqa: BLE001 - never let signing break a response
            logger.warning(f"Failed to presign URL {url}: {e}")
            return url

    async def upload_file(self, file: UploadFile, folder: str) -> str:
        """
        Upload a file to S3.

        Args:
            file: The uploaded file.
            folder: S3 folder path, e.g. 'avatars/users'.

        Returns:
            The public URL of the uploaded file.
        """
        # Validate content type
        content_type = file.content_type or ""
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type '{content_type}'. Allowed: JPEG, PNG, WebP",
            )

        # Read file and validate size
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB",
            )

        # Generate unique filename
        ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
        unique_name = f"{uuid.uuid4().hex}.{ext}"
        key = f"{folder}/{unique_name}"

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=contents,
                ContentType=content_type,
            )
            logger.info(f"Uploaded file to S3: {key}")
            return self._build_url(key)
        except ClientError as e:
            logger.error(f"S3 upload error: {e}")
            raise HTTPException(status_code=500, detail="Failed to upload file")

    async def delete_file(self, file_url: str) -> bool:
        """
        Delete a file from S3 by its URL.

        Args:
            file_url: The full URL of the file to delete.

        Returns:
            True if deleted successfully.
        """
        key = self._key_from_url(file_url)
        if not key:
            logger.warning(f"Could not extract S3 key from URL: {file_url}")
            return False

        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            logger.info(f"Deleted file from S3: {key}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete error: {e}")
            return False


# Singleton instance
s3_service = S3Service()

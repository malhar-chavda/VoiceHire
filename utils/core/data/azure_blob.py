from __future__ import annotations
"""
Azure Blob Storage service handles file uploads.

Audio blobs are stored in a private container and returned as
SAS URLs (1-hour expiry) so the browser can stream them directly
without needing account-level public access.
"""


import asyncio
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import BinaryIO

from azure.storage.blob import (
    BlobServiceClient,
    ContentSettings,
    generate_blob_sas,
    BlobSasPermissions,
)
from constants.config import settings

logger = logging.getLogger(__name__)

_CONTAINER_MAP = {
    "resumes": "resumes",
    "audio": "audio",
    "jds": "jds",
}

# Audio blobs are private; we issue SAS URLs with this expiry
_AUDIO_SAS_EXPIRY_HOURS = 2  


class BlobStorageService:
    """Manages file uploads to Azure Blob Storage."""

    def _client(self) -> BlobServiceClient:
        return BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )

    def _sas_url(self, container_name: str, blob_name: str) -> str:
        """Generate a time-limited SAS URL for a private blob."""
        client = self._client()
        account_name = client.account_name
        account_key  = client.credential.account_key   # extracted from connection string

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=_AUDIO_SAS_EXPIRY_HOURS),
        )
        return (
            f"https://{account_name}.blob.core.windows.net"
            f"/{container_name}/{blob_name}?{sas_token}"
        )

    async def upload(
        self,
        file_data: bytes | BinaryIO,
        filename: str,
        folder: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload a file and return a URL.

        Container routing:
            folder='resumes'  ? resumes container
            folder='audio'    ? audio   container  (private; returns SAS URL)
            anything else     ? jds     container
        """
        container_name = _CONTAINER_MAP.get(folder, "jds")
        blob_name      = f"{uuid.uuid4()}_{filename}"

        def _upload() -> str:
            client           = self._client()
            container_client = client.get_container_client(container_name)

            # Ensure container exists always PRIVATE (public access disabled at account level)
            if not container_client.exists():
                container_client.create_container()   # no public_access arg ? private
                logger.info("Created container: %s", container_name)

            blob_client = container_client.get_blob_client(blob_name)
            blob_client.upload_blob(
                file_data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )
            blob_url = blob_client.url
            logger.info("Uploaded blob: %s", blob_url)

            # Audio files: return a SAS URL so the browser can stream without public access
            if container_name == "audio":
                sas = self._sas_url(container_name, blob_name)
                logger.info("Audio SAS URL (2h): %s", sas[:80] + "...")
                return sas

            return blob_url

        return await asyncio.to_thread(_upload)

    def delete(self, blob_url: str) -> None:
        """Delete a blob by its full URL (ignores SAS token if present)."""
        clean = blob_url.split("?")[0]    # strip SAS query string
        parts = clean.split("/")
        container_name = parts[3]
        blob_name      = "/".join(parts[4:])
        client = self._client()
        client.get_container_client(container_name).get_blob_client(blob_name).delete_blob()
        logger.info("Deleted blob: %s", clean)

blob_storage = BlobStorageService() 
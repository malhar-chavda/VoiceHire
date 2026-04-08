# helper function which manages the Azure Blob Storage
# handles uploading PDF files and generating URLs for the dashboard.
# the client that uploads and downloads files from Aure Storage

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from typing import BinaryIO

from azure.storage.blob import BlobServiceClient, ContentSettings  
from utils.settings import settings


def _get_client() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING
    )

# uploading PDF files and generating URLs for the dashboard.
async def upload_file(
    file_data: bytes | BinaryIO,
    filename: str, 
    folder: str,                                # resumes or job_descriptions
    content_type: str = "application/octet-stream",  
) -> str:
    """
    Upload a file to Azure Blob Storage to a specific container based on the folder.
    Returns the full blob URL string.
    """
    client = _get_client() 
    
    container_name = "resumes" if folder == "resumes" else "jds"
    container = client.get_container_client(container_name)
    
    blob_name = f"{uuid.uuid4()}_{filename}"
    blob_client = container.get_blob_client(blob_name)

    my_content_settings = ContentSettings(content_type=content_type)
    blob_client.upload_blob(
        file_data,
        overwrite=True,
        content_settings=my_content_settings
    )

    return blob_client.url


def delete_file(blob_url: str) -> None:
    """
    Delete a blob given its full URL.
    Used for cleanup on failed pipeline runs.
    """
    client = _get_client()
    
    # Extract container and blob name from URL: 
    # https://<account>.blob.core.windows.net/<container>/<blob_name>
    parts = blob_url.split("/")
    container_name = parts[3]
    blob_name = "/".join(parts[4:])
    
    container = client.get_container_client(container_name)
    container.get_blob_client(blob_name).delete_blob()
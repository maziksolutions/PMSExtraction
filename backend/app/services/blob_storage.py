from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Iterator, Union

logger = logging.getLogger(__name__)


class BlobStorageService:
    """
    Storage abstraction that works over MinIO (local dev) or Azure Blob
    Storage (production).

    Selection is driven by environment variables:
      - If AZURE_STORAGE_ACCOUNT is set, use Azure Blob Storage.
      - Otherwise use MinIO via the S3-compatible API.
    """

    def __init__(self) -> None:
        from app.core.config import settings

        self._settings = settings
        self._use_azure = bool(settings.AZURE_STORAGE_ACCOUNT)
        self._client: Any = None

        if self._use_azure:
            self._init_azure()
        else:
            self._init_minio()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_minio(self) -> None:
        from minio import Minio

        s = self._settings
        endpoint = s.MINIO_ENDPOINT.replace("http://", "").replace("https://", "")
        secure = s.MINIO_ENDPOINT.startswith("https://")

        self._client = Minio(
            endpoint,
            access_key=s.MINIO_ACCESS_KEY,
            secret_key=s.MINIO_SECRET_KEY,
            secure=secure,
        )
        self._bucket = s.MINIO_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info("Created MinIO bucket: %s", self._bucket)
        except Exception as exc:
            logger.warning("Could not ensure MinIO bucket exists: %s", exc)

    def _init_azure(self) -> None:
        from azure.storage.blob import BlobServiceClient

        s = self._settings
        conn_str = (
            f"DefaultEndpointsProtocol=https;"
            f"AccountName={s.AZURE_STORAGE_ACCOUNT};"
            f"AccountKey={s.AZURE_STORAGE_KEY};"
            f"EndpointSuffix=core.windows.net"
        )
        self._client = BlobServiceClient.from_connection_string(conn_str)
        self._bucket = s.AZURE_STORAGE_CONTAINER

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def upload_stream(
        self,
        key: str,
        stream: Union[AsyncIterator[bytes], Any],
        content_type: str,
    ) -> str:
        """
        Upload a file stream to blob storage.
        Accepts both sync iterables and async generators.
        Returns the storage key.
        """
        import asyncio
        import io

        # Collect async stream into bytes
        chunks: list[bytes] = []
        if hasattr(stream, "__aiter__"):
            async for chunk in stream:
                chunks.append(chunk)
        else:
            for chunk in stream:
                chunks.append(chunk)

        data = b"".join(chunks)
        size = len(data)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._upload_bytes,
            key,
            io.BytesIO(data),
            size,
            content_type,
        )
        return key

    def upload_stream_sync(
        self,
        key: str,
        stream: Union[Iterator[bytes], Any],
        content_type: str,
    ) -> str:
        """
        Synchronous upload for use inside Celery tasks.
        Returns the storage key.
        """
        import io

        if hasattr(stream, "read"):
            data = stream.read()
        else:
            data = b"".join(stream)

        self._upload_bytes(key, io.BytesIO(data), len(data), content_type)
        return key

    def _upload_bytes(
        self,
        key: str,
        data_stream: Any,
        size: int,
        content_type: str,
    ) -> None:
        if self._use_azure:
            container_client = self._client.get_container_client(self._bucket)
            blob_client = container_client.get_blob_client(key)
            blob_client.upload_blob(
                data_stream,
                length=size,
                content_settings={"content_type": content_type},
                overwrite=True,
            )
        else:
            self._client.put_object(
                self._bucket,
                key,
                data_stream,
                size,
                content_type=content_type,
            )

    async def get_download_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Return a pre-signed URL giving temporary access to the object.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._get_presigned_url, key, expires_in
        )

    def _get_presigned_url(self, key: str, expires_in: int) -> str:
        if self._use_azure:
            from datetime import datetime, timedelta, timezone

            from azure.storage.blob import (
                BlobSasPermissions,
                generate_blob_sas,
            )

            s = self._settings
            sas_token = generate_blob_sas(
                account_name=s.AZURE_STORAGE_ACCOUNT,
                container_name=self._bucket,
                blob_name=key,
                account_key=s.AZURE_STORAGE_KEY,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            )
            return (
                f"https://{s.AZURE_STORAGE_ACCOUNT}.blob.core.windows.net"
                f"/{self._bucket}/{key}?{sas_token}"
            )
        else:
            from datetime import timedelta

            url = self._client.presigned_get_object(
                self._bucket,
                key,
                expires=timedelta(seconds=expires_in),
            )
            return url

    async def delete_object(self, key: str) -> None:
        """Remove an object from blob storage."""
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._delete_sync, key)

    def _delete_sync(self, key: str) -> None:
        if self._use_azure:
            container_client = self._client.get_container_client(self._bucket)
            container_client.delete_blob(key, delete_snapshots="include")
        else:
            self._client.remove_object(self._bucket, key)

    async def download_bytes(self, key: str) -> bytes:
        """
        Download an entire object as bytes. Used by classification and extraction tasks.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._download_bytes_sync, key)

    def _download_bytes_sync(self, key: str) -> bytes:
        chunks = list(self.get_object_stream(key))
        return b"".join(chunks)

    def get_object_stream(self, key: str) -> Iterator[bytes]:
        """
        Return a streaming iterator for reading an object.
        For Celery tasks that need sync access.
        """
        if self._use_azure:
            container_client = self._client.get_container_client(self._bucket)
            blob_client = container_client.get_blob_client(key)
            downloader = blob_client.download_blob()
            yield from downloader.chunks()
        else:
            response = self._client.get_object(self._bucket, key)
            try:
                yield from response.stream(65536)
            finally:
                response.close()
                response.release_conn()

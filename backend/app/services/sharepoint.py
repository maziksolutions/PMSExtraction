from __future__ import annotations

import logging
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "png", "jpg", "jpeg", "tiff"}


class SharePointService:
    """
    Thin wrapper around the Microsoft Graph API for SharePoint file operations.
    All methods are async and expect a valid Azure AD access token.
    """

    def __init__(self, access_token: str) -> None:
        self.token = access_token
        self.graph_base = "https://graph.microsoft.com/v1.0"
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def list_folder_contents(self, folder_url: str) -> List[Dict[str, Any]]:
        """
        List files inside a SharePoint folder using the Microsoft Graph API
        driveItem children endpoint.

        Returns a list of dicts:
            {name, path, size, mimeType, webUrl}

        Only files with supported extensions are returned.
        """
        site_id, drive_path = self._parse_folder_url(folder_url)

        async with httpx.AsyncClient(timeout=30) as client:
            url = (
                f"{self.graph_base}/sites/{site_id}"
                f"/drive/root:/{drive_path}:/children"
            )
            items: List[Dict[str, Any]] = []
            next_link: str | None = url

            while next_link:
                resp = await client.get(next_link, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()

                for item in data.get("value", []):
                    # Skip folders
                    if "folder" in item:
                        continue

                    name: str = item.get("name", "")
                    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                    if ext not in ALLOWED_EXTENSIONS:
                        continue

                    items.append(
                        {
                            "name": name,
                            "path": item.get("parentReference", {}).get("path", "")
                            + "/"
                            + name,
                            "size": item.get("size", 0),
                            "mimeType": item.get("file", {}).get(
                                "mimeType", "application/octet-stream"
                            ),
                            "webUrl": item.get("webUrl", ""),
                        }
                    )

                next_link = data.get("@odata.nextLink")

        return items

    async def get_download_url(self, file_path: str) -> str:
        """
        Retrieve a temporary @microsoft.graph.downloadUrl for a SharePoint file.
        """
        site_id, _ = self._parse_folder_url(file_path)
        relative_path = file_path.lstrip("/")

        async with httpx.AsyncClient(timeout=30) as client:
            url = f"{self.graph_base}/sites/{site_id}/drive/root:/{relative_path}"
            resp = await client.get(url, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

        download_url = data.get("@microsoft.graph.downloadUrl")
        if not download_url:
            raise ValueError(
                f"No downloadUrl found for path '{file_path}'. "
                "Ensure the file exists and the token has Files.Read permissions."
            )
        return download_url

    async def stream_download(self, download_url: str, dest_key: str) -> int:
        """
        Stream-download a file from a pre-signed SharePoint download URL and
        upload it directly to blob storage.

        Returns the total number of bytes written.
        """
        from app.services.blob_storage import BlobStorageService

        blob_service = BlobStorageService()
        total_bytes = 0

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30, read=300, write=300, pool=10),
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", download_url) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get(
                    "content-type", "application/octet-stream"
                )

                async def _chunk_gen():
                    nonlocal total_bytes
                    async for chunk in resp.aiter_bytes(65536):
                        total_bytes += len(chunk)
                        yield chunk

                await blob_service.upload_stream(dest_key, _chunk_gen(), content_type)

        return total_bytes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_folder_url(folder_url: str) -> tuple[str, str]:
        """
        Extract (site_id_or_hostname, drive_path) from a SharePoint URL.

        Supports formats:
          https://{tenant}.sharepoint.com/sites/{site}/Shared Documents/{path}
          https://graph.microsoft.com/v1.0/sites/{site_id}/...
        """
        parsed = urlparse(folder_url)
        hostname = parsed.netloc  # e.g. "contoso.sharepoint.com"
        path_parts = [p for p in parsed.path.split("/") if p]

        # Locate /sites/{site_name} in path
        try:
            sites_idx = path_parts.index("sites")
            site_name = path_parts[sites_idx + 1]
            site_id = f"{hostname}:/sites/{site_name}"
            # Everything after /sites/{site_name} is the drive path
            drive_path = "/".join(path_parts[sites_idx + 2:])
        except (ValueError, IndexError):
            # Fallback: treat the whole path as the drive path and use hostname as site
            site_id = hostname
            drive_path = parsed.path.lstrip("/")

        return site_id, drive_path

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "png", "jpg", "jpeg", "tiff"}
_MAX_DEPTH = 6  # maximum folder recursion depth


class SharePointService:
    """
    Wrapper around Microsoft Graph API for SharePoint file operations.
    Authenticates via client-credentials flow using environment variables:
      AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET
    """

    def __init__(self, access_token: Optional[str] = None) -> None:
        if not access_token:
            access_token = self._get_client_credentials_token()
        self.token = access_token
        self.graph_base = "https://graph.microsoft.com/v1.0"
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # Client-credentials token (app-level, no user consent required)
    # ------------------------------------------------------------------

    @staticmethod
    def _get_client_credentials_token() -> str:
        """
        Obtain an OAuth2 token using the client-credentials flow.
        Requires AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET.
        The registered app needs Sites.Read.All and Files.Read.All app permissions.
        """
        from app.core.config import settings

        tenant_id = getattr(settings, "AZURE_TENANT_ID", None)
        client_id = getattr(settings, "AZURE_CLIENT_ID", None)
        client_secret = getattr(settings, "AZURE_CLIENT_SECRET", None)

        if not (tenant_id and client_id and client_secret):
            raise ValueError(
                "AZURE_TENANT_ID, AZURE_CLIENT_ID and AZURE_CLIENT_SECRET "
                "must be set to use SharePoint integration."
            )

        token_url = (
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        )
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(token_url, data=data)
            resp.raise_for_status()
            return resp.json()["access_token"]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def list_folder_contents(self, folder_url: str) -> List[Dict[str, Any]]:
        """
        Recursively list ALL files inside a SharePoint folder (including sub-folders).

        Returns a list of dicts:
            {name, path, size, mimeType, webUrl, download_url, folder_path}

        Only files with supported extensions are returned.
        """
        site_id, drive_path = self._parse_folder_url(folder_url)

        async with httpx.AsyncClient(timeout=60) as client:
            drive_id: Optional[str] = None

            if drive_path:
                # The first path segment may be a document library name (a separate Drive).
                # Try to resolve it via the /drives endpoint so we use the correct drive,
                # not just the site's default "Documents" drive.
                parts = drive_path.split("/", 1)
                library_name = parts[0]
                sub_path = parts[1] if len(parts) > 1 else ""

                drive_id = await self._find_drive_id(client, site_id, library_name)

                if drive_id:
                    if sub_path:
                        start_url = (
                            f"{self.graph_base}/sites/{site_id}"
                            f"/drives/{drive_id}/root:/{sub_path}:/children"
                        )
                    else:
                        start_url = (
                            f"{self.graph_base}/sites/{site_id}"
                            f"/drives/{drive_id}/root/children"
                        )
                else:
                    # Fall back: treat as subfolder of the default drive
                    start_url = (
                        f"{self.graph_base}/sites/{site_id}"
                        f"/drive/root:/{drive_path}:/children"
                    )
            else:
                start_url = f"{self.graph_base}/sites/{site_id}/drive/root/children"

            items = await self._list_recursive(client, site_id, url=start_url, depth=0, drive_id=drive_id)

        return items

    async def _find_drive_id(self, client: httpx.AsyncClient, site_id: str, library_name: str) -> Optional[str]:
        """Return the Graph drive ID whose name matches library_name (case-insensitive), or None."""
        try:
            url = f"{self.graph_base}/sites/{site_id}/drives"
            resp = await client.get(url, headers=self._headers)
            resp.raise_for_status()
            for drive in resp.json().get("value", []):
                if drive.get("name", "").lower() == library_name.lower():
                    return drive["id"]
        except Exception as err:
            logger.warning("Could not list drives for site %s: %s", site_id, err)
        return None

    async def _list_recursive(
        self,
        client: httpx.AsyncClient,
        site_id: str,
        url: str,
        depth: int,
        folder_path: str = "",
        drive_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Recursively traverse folders using the Graph API children endpoint."""
        if depth > _MAX_DEPTH:
            logger.warning("Max recursion depth %d reached at %s", _MAX_DEPTH, folder_path)
            return []

        items: List[Dict[str, Any]] = []
        next_link: Optional[str] = url

        while next_link:
            resp = await client.get(next_link, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("value", []):
                name: str = item.get("name", "")
                item_id: str = item.get("id", "")
                current_path = f"{folder_path}/{name}" if folder_path else name

                if "folder" in item:
                    # Recurse using item ID; use the specific drive if known
                    if drive_id:
                        sub_url = (
                            f"{self.graph_base}/sites/{site_id}"
                            f"/drives/{drive_id}/items/{item_id}/children"
                        )
                    else:
                        sub_url = (
                            f"{self.graph_base}/sites/{site_id}"
                            f"/drive/items/{item_id}/children"
                        )
                    sub_items = await self._list_recursive(
                        client, site_id, url=sub_url,
                        depth=depth + 1, folder_path=current_path, drive_id=drive_id,
                    )
                    items.extend(sub_items)
                    continue

                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in ALLOWED_EXTENSIONS:
                    continue

                # Store the pre-signed download URL so the task can use it directly
                download_url = item.get("@microsoft.graph.downloadUrl", "")
                if not download_url:
                    # Request it explicitly when not included in the listing
                    try:
                        meta_resp = await client.get(
                            f"{self.graph_base}/sites/{site_id}/drive/items/{item_id}",
                            headers={**self._headers, "Prefer": "allowthrottleablequeries"},
                        )
                        meta_resp.raise_for_status()
                        download_url = meta_resp.json().get("@microsoft.graph.downloadUrl", "")
                    except Exception as err:
                        logger.warning("Could not get download URL for %s: %s", name, err)

                items.append(
                    {
                        "name": name,
                        "path": download_url or current_path,  # pre-signed URL or fallback
                        "size": item.get("size", 0),
                        "mimeType": item.get("file", {}).get(
                            "mimeType", "application/octet-stream"
                        ),
                        "webUrl": item.get("webUrl", ""),
                        "download_url": download_url,
                        "folder_path": folder_path,
                        "modified": item.get("lastModifiedDateTime", ""),
                    }
                )

            next_link = data.get("@odata.nextLink")

        return items

    async def get_download_url(self, file_path: str) -> str:
        """
        Retrieve a temporary download URL for a SharePoint file.
        If file_path is already a pre-signed https:// URL, return it as-is.
        """
        if file_path.startswith("https://"):
            return file_path

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
        Extract (site_id, drive_path) from a SharePoint URL.

        Handles:
          https://{tenant}.sharepoint.com/sites/{site}/Shared Documents/{path}
          https://{tenant}.sharepoint.com/sites/{site}/LibraryName/Forms/AllItems.aspx
          https://{tenant}.sharepoint.com/sites/{site}/LibraryName/{subfolder}
        """
        parsed = urlparse(folder_url)
        hostname = parsed.netloc
        path_parts = [p for p in parsed.path.split("/") if p]

        # Locate /sites/{site_name} in path
        try:
            sites_idx = path_parts.index("sites")
            site_name = path_parts[sites_idx + 1]
            site_id = f"{hostname}:/sites/{site_name}"
            remaining = path_parts[sites_idx + 2:]

            # Strip SharePoint UI fragments (Forms, AllItems.aspx, etc.)
            ui_stops = {"Forms", "AllItems.aspx", "_layouts", "Shared%20Documents"}
            clean = []
            for part in remaining:
                if part in ui_stops or part.endswith(".aspx"):
                    break
                clean.append(part)

            drive_path = "/".join(clean)
        except (ValueError, IndexError):
            site_id = hostname
            drive_path = parsed.path.lstrip("/")

        return site_id, drive_path

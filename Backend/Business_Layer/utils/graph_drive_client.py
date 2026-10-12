# Backend/Business_Layer/utils/graph_drive_client.py
"""Microsoft Graph client for ONE SharePoint document library (bulk-import pickup, 6.7).

Same app-only sign-in as the mail client (TENANT_ID / CLIENT_ID / CLIENT_SECRET); the token never
leaves this process. The app should be granted `Sites.Selected` with write access on the AP site
only - not tenant-wide Files / Sites permissions.

.env:
    SHAREPOINT_SITE          e.g. pavestechnologies.sharepoint.com:/sites/APAutomation
    SHAREPOINT_LIBRARY       document library name, default "Documents"
    SHAREPOINT_ROOT_FOLDER   folder inside the library, default "AP Imports"
"""
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from Backend.Business_Layer.utils.graph_mail_client import GRAPH, GraphMailClient, GraphMailError
from Backend.config.env_loader import get_env_var

logger = logging.getLogger(__name__)
_TIMEOUT = 120


class GraphDriveError(GraphMailError):
    pass


class GraphDriveClient(GraphMailClient):
    def __init__(self, session: Optional[requests.Session] = None):
        # Mailbox is irrelevant here - satisfy the base check, then read the site settings.
        super().__init__(mailbox="unused", session=session)
        self.site = (get_env_var("SHAREPOINT_SITE", "") or "").strip()
        self.library = (get_env_var("SHAREPOINT_LIBRARY", "Documents") or "Documents").strip()
        self.root = (get_env_var("SHAREPOINT_ROOT_FOLDER", "AP Imports") or "AP Imports").strip().strip("/")
        if not self.site:
            raise GraphDriveError("SharePoint pickup is not configured: set SHAREPOINT_SITE in .env")
        self._drive_id: Optional[str] = None

    # ------------------------------------------------------------------
    def _send(self, method: str, url: str, **kwargs):
        for attempt in range(4):
            response = self.http.request(method, url, timeout=_TIMEOUT,
                                         headers={"Authorization": f"Bearer {self._access_token()}", **kwargs.pop("headers", {})},
                                         **kwargs)
            if response.status_code in (429, 503) and attempt < 3:
                time.sleep(min(int(response.headers.get("Retry-After", 2 ** attempt)), 60))
                continue
            if response.status_code >= 400:
                try:
                    code = response.json().get("error", {}).get("code", "")
                except ValueError:
                    code = ""
                raise GraphDriveError(f"SharePoint request failed (HTTP {response.status_code}{', ' + code if code else ''}).")
            return response
        raise GraphDriveError("SharePoint kept throttling the request; try again later.")

    def drive_id(self) -> str:
        if self._drive_id:
            return self._drive_id
        site = self._get(f"{GRAPH}/sites/{self.site}")
        drives = self._get(f"{GRAPH}/sites/{site['id']}/drives").get("value", [])
        match = next((d for d in drives if d.get("name", "").lower() == self.library.lower()), None)
        if match is None:
            raise GraphDriveError(f"Document library '{self.library}' not found on the SharePoint site")
        self._drive_id = match["id"]
        return self._drive_id

    def _path_url(self, path: str) -> str:
        return f"{GRAPH}/drives/{self.drive_id()}/root:/{quote(path.strip('/'))}"

    def children(self, folder: str) -> List[Dict[str, Any]]:
        """Files (not sub-folders) in root/<folder>; [] when the folder does not exist yet."""
        url = self._path_url(f"{self.root}/{folder}") + ":/children"
        items: List[Dict[str, Any]] = []
        try:
            while url:
                page = self._get(url, {"$select": "id,name,eTag,size,file,folder,lastModifiedBy,lastModifiedDateTime"} if "?" not in url else None)
                items.extend(i for i in page.get("value", []) if "file" in i)
                url = page.get("@odata.nextLink")
        except GraphMailError as exc:
            if "HTTP 404" in str(exc):
                return []
            raise
        return items

    def download(self, item_id: str) -> bytes:
        return self._get(f"{GRAPH}/drives/{self.drive_id()}/items/{quote(item_id)}/content", raw=True)

    def ensure_folder(self, path: str) -> str:
        """Creates root/<path> (each level) if needed; returns its item id."""
        parent_url = f"{GRAPH}/drives/{self.drive_id()}/root"
        current = ""
        item_id = None
        for part in [p for p in f"{self.root}/{path}".split("/") if p]:
            current = f"{current}/{part}" if current else part
            try:
                item_id = self._get(self._path_url(current))["id"]
            except GraphMailError:
                created = self._send("POST", f"{parent_url}/children",
                                     json={"name": part, "folder": {}, "@microsoft.graph.conflictBehavior": "replace"}).json()
                item_id = created["id"]
            parent_url = f"{GRAPH}/drives/{self.drive_id()}/items/{item_id}"
        return item_id

    def move(self, item_id: str, folder_id: str, new_name: Optional[str] = None) -> None:
        body: Dict[str, Any] = {"parentReference": {"id": folder_id}}
        if new_name:
            body["name"] = new_name
        self._send("PATCH", f"{GRAPH}/drives/{self.drive_id()}/items/{quote(item_id)}?@microsoft.graph.conflictBehavior=rename", json=body)

    def upload(self, folder_id: str, name: str, content: bytes) -> None:
        """Small-file upload (< 4 MB - result sheets)."""
        self._send("PUT", f"{GRAPH}/drives/{self.drive_id()}/items/{quote(folder_id)}:/{quote(name)}:/content",
                   data=content, headers={"Content-Type": "application/octet-stream"})

# Backend/Business_Layer/utils/graph_mail_client.py
"""Minimal read-only Microsoft Graph mail client for email invoice intake (Phase 3b).

App-only auth (client credentials: CLIENT_ID / CLIENT_SECRET / TENANT_ID from .env). The access
token stays in this process - it is never returned, logged or sent anywhere but Graph. Only GET
calls are made, so the app registration needs just the Mail.Read application permission (ideally
limited to the intake mailbox with an Exchange Application Access Policy).
"""
import logging
import time
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import quote

import requests

from Backend.config.env_loader import get_env_var

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
_TIMEOUT = 60
_MAX_RETRIES = 4


class GraphMailError(RuntimeError):
    """Graph returned an error; the message never contains credentials or tokens."""


class GraphMailClient:
    def __init__(self, mailbox: Optional[str] = None, session: Optional[requests.Session] = None):
        self.tenant_id = get_env_var("TENANT_ID")
        self.client_id = get_env_var("CLIENT_ID")
        self.client_secret = get_env_var("CLIENT_SECRET")
        self.mailbox = mailbox or get_env_var("MAIL_ADDRESS")
        if not all([self.tenant_id, self.client_id, self.client_secret, self.mailbox]):
            raise GraphMailError("Email intake is not configured: TENANT_ID, CLIENT_ID, CLIENT_SECRET and MAIL_ADDRESS are required in .env")
        self.http = session or requests.Session()
        self._token: Optional[str] = None
        self._token_expires = 0.0

    # ------------------------------------------------------------------
    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 120:
            return self._token
        response = self.http.post(
            f"https://login.microsoftonline.com/{quote(self.tenant_id)}/oauth2/v2.0/token",
            data={"client_id": self.client_id, "client_secret": self.client_secret,
                  "grant_type": "client_credentials", "scope": "https://graph.microsoft.com/.default"},
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            # Only Azure's error code is surfaced (e.g. invalid_client) - never the request.
            code = (response.json() if response.headers.get("content-type", "").startswith("application/json") else {}).get("error")
            raise GraphMailError(f"Could not sign in to Microsoft Graph (HTTP {response.status_code}{', ' + code if code else ''}).")
        body = response.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    def _get(self, url: str, params: Optional[Dict[str, str]] = None, raw: bool = False):
        for attempt in range(_MAX_RETRIES + 1):
            response = self.http.get(url, params=params, timeout=_TIMEOUT,
                                     headers={"Authorization": f"Bearer {self._access_token()}"})
            if response.status_code in (429, 503, 504) and attempt < _MAX_RETRIES:
                wait = min(int(response.headers.get("Retry-After", 2 ** attempt)), 60)
                logger.warning("Graph throttled (HTTP %s), retrying in %ss", response.status_code, wait)
                time.sleep(wait)
                continue
            if response.status_code == 401 and attempt == 0:
                self._token = None  # expired early - sign in again once
                continue
            if response.status_code != 200:
                try:
                    detail = response.json().get("error", {}).get("code", "")
                except ValueError:
                    detail = ""
                raise GraphMailError(f"Microsoft Graph request failed (HTTP {response.status_code}{', ' + detail if detail else ''}).")
            return response.content if raw else response.json()
        raise GraphMailError("Microsoft Graph kept throttling the request; try again later.")

    def _user_path(self) -> str:
        return f"{GRAPH}/users/{quote(self.mailbox)}"

    # ------------------------------------------------------------------
    def messages_since(self, since_iso: str, page_size: int = 50) -> Iterator[Dict[str, Any]]:
        """Inbox messages received at/after ``since_iso`` (UTC, ISO-8601), oldest first."""
        url = f"{self._user_path()}/mailFolders/inbox/messages"
        params = {
            "$filter": f"receivedDateTime ge {since_iso}",
            "$orderby": "receivedDateTime asc",
            "$select": "id,internetMessageId,subject,from,receivedDateTime,hasAttachments",
            "$top": str(page_size),
        }
        while url:
            page = self._get(url, params)
            yield from page.get("value", [])
            url, params = page.get("@odata.nextLink"), None

    def attachments(self, message_id: str) -> List[Dict[str, Any]]:
        """Attachment metadata only (no content)."""
        page = self._get(f"{self._user_path()}/messages/{quote(message_id)}/attachments",
                         {"$select": "id,name,contentType,size,isInline"})
        return page.get("value", [])

    def attachment_bytes(self, message_id: str, attachment_id: str) -> bytes:
        return self._get(f"{self._user_path()}/messages/{quote(message_id)}/attachments/{quote(attachment_id)}/$value",
                         raw=True)

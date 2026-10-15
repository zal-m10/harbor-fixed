"""
Tempik disposable email API wrapper.
Base URL and domains read from config.toml.
"""

import requests
import tomllib
from pathlib import Path
from typing import Optional

# Load config — always relative to this file's directory
_CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"


def _load_config() -> dict:
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


BASE_URL = _load_config()["tempik"]["base_url"]


class TempikClient:
    """Minimal temp-mail client for TokenHarbor signup verification."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self._session_id: Optional[str] = None
        self._domains: Optional[list[str]] = None

    def _ensure_session(self) -> str:
        if not self._session_id:
            r = self.session.get(f"{BASE_URL}/api/session")
            r.raise_for_status()
            self._session_id = r.json()["sessionId"]
        return self._session_id

    @property
    def _headers(self) -> dict:
        return {"x-session-id": self._ensure_session()}

    def get_domains(self) -> list[str]:
        """Fetch and cache available domains from Tempik config."""
        if self._domains is None:
            r = self.session.get(f"{BASE_URL}/api/config")
            r.raise_for_status()
            self._domains = r.json().get("mailDomains", ["exse7en.fr"])
        return self._domains

    def get_config(self) -> dict:
        r = self.session.get(f"{BASE_URL}/api/config")
        r.raise_for_status()
        return r.json()

    def create_inbox(self, local_part: str = "", domain: str = "") -> dict:
        """Create a disposable inbox. Random if local_part is empty."""
        payload = {}
        if local_part:
            payload["localPart"] = local_part
        if domain:
            payload["domain"] = domain
        r = self.session.post(
            f"{BASE_URL}/api/inboxes",
            headers=self._headers,
            json=payload,
        )
        r.raise_for_status()
        return r.json()

    def get_messages(self, address: str) -> list[dict]:
        r = self.session.get(
            f"{BASE_URL}/api/inboxes/{address}/messages",
            headers=self._headers,
        )
        r.raise_for_status()
        return r.json()

    def wait_for_message(
        self, address: str, timeout: float = 120, poll_interval: float = 3
    ) -> Optional[dict]:
        """Poll until a message arrives. Returns the first message or None."""
        import time

        deadline = time.time() + timeout
        while time.time() < deadline:
            messages = self.get_messages(address)
            if messages:
                return messages[0]
            time.sleep(poll_interval)
        return None

    def delete_inbox(self, address: str) -> None:
        r = self.session.delete(
            f"{BASE_URL}/api/inboxes/{address}",
            headers=self._headers,
        )
        r.raise_for_status()
"""Disposable inbox client for tempmail.lol (v2 API).

Drop-in alternative to TempikClient for TokenHarbor signup verification.
No setup needed -- inboxes are created on demand via the public API.
"""
from __future__ import annotations

import time
from typing import Optional

import requests

API_BASE = "https://api.tempmail.lol/v2"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


class TempMailLolClient:
    """Minimal tempmail.lol client matching the TempikClient interface."""

    def __init__(self, timeout: float = 30):
        self._s = requests.Session()
        self._s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._timeout = timeout
        self._token: Optional[str] = None

    def create_inbox(self, local_part: str = "", domain: str = "") -> dict:
        """Create a disposable inbox. tempmail.lol assigns the address."""
        for _ in range(12):
            try:
                r = self._s.post(f"{API_BASE}/inbox/create", timeout=self._timeout)
            except Exception:
                time.sleep(8)
                continue
            if r.status_code != 201:
                time.sleep(8)
                continue
            try:
                d = r.json()
                addr, tok = d["address"], d["token"]
            except Exception:
                time.sleep(8)
                continue
            if self._has_mx(addr.split("@")[1]):
                self._token = tok
                return {"address": addr}
            time.sleep(5)
        raise RuntimeError("tempmail.lol inbox create failed after 12 tries")

    def wait_for_message(self, address: str, timeout: float = 120,
                         poll_interval: float = 5):
        """Poll the inbox until an email arrives. Returns {'body': ...} or None."""
        if not self._token:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = self._s.get(f"{API_BASE}/inbox?token={self._token}",
                                timeout=self._timeout)
            except Exception:
                time.sleep(poll_interval)
                continue
            if r.status_code == 200:
                try:
                    emails = r.json().get("emails", [])
                except Exception:
                    emails = []
                if emails:
                    e = emails[0]
                    raw = ((e.get("subject") or "") + "\n" +
                           (e.get("body") or "") + "\n" +
                           (e.get("html") or ""))
                    return {"body": raw}
            time.sleep(poll_interval)
        return None

    @staticmethod
    def _has_mx(domain: str) -> bool:
        """MX pre-check via DNS-over-HTTPS. Fail-open on error."""
        try:
            r = requests.get(
                "https://cloudflare-dns.com/dns-query",
                params={"name": domain, "type": "MX"},
                headers={"Accept": "application/dns-json"},
                timeout=10,
            )
            return bool(r.json().get("Answer"))
        except Exception:
            return True

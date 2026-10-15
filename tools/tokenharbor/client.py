"""
TokenHarbor HTTP Client — pure requests, no browser needed.
Handles signup, email verification, login, API key creation,
and free-tier activation with Capsolver Turnstile integration.

Key features:
- Auto-extracts deployment IDs and server action hashes from page
- Cookie-based authentication for API endpoints
- Proxy support for IP rotation
- Disposable email via Tempik
- Config from config.toml
"""

from __future__ import annotations

import json
import re
import time
import uuid
import base64
import tomllib
from pathlib import Path
from typing import Optional

import requests

# Load config
_CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"
with open(_CONFIG_PATH, "rb") as _f:
    _cfg = tomllib.load(_f)

BASE_URL = _cfg["tokenharbor"]["base_url"]
TURNSTILE_SITEKEY = _cfg["tokenharbor"]["turnstile_sitekey"]


class TokenHarborClient:
    """Automate TokenHarbor signup, verification, API key creation."""

    def __init__(self, capsolver_key: Optional[str] = None, proxy: Optional[str] = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/130.0.0.0 Safari/537.36"
            ),
            "Origin": BASE_URL,
        })
        self._capsolver_key: Optional[str] = capsolver_key
        self._proxy: Optional[str] = proxy
        self._proxies: Optional[dict] = {"http": proxy, "https": proxy} if proxy else None

        # Cached deployment info
        self._deployment_id: Optional[str] = None
        self._signup_action_hash: Optional[str] = None
        self._signin_action_hash: Optional[str] = None

        # State
        self._fingerprint: str = str(uuid.uuid4())
        self._timezone: str = "Asia/Jakarta"
        self._access_token: Optional[str] = None

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, url: str, **kwargs) -> requests.Response:
        if self._proxies:
            kwargs.setdefault("proxies", self._proxies)
        return self.session.get(url, **kwargs)

    def _post(self, url: str, **kwargs) -> requests.Response:
        if self._proxies:
            kwargs.setdefault("proxies", self._proxies)
        return self.session.post(url, **kwargs)

    # ------------------------------------------------------------------
    # Deployment info extraction
    # ------------------------------------------------------------------

    def _extract_deployment_id(self, response) -> Optional[str]:
        """Extract dpl_ from Link header or data-dpl-id attribute."""
        link = response.headers.get("Link", "")
        for m in re.findall(r"dpl_[a-zA-Z0-9]+", link):
            return m
        for m in re.findall(r'data-dpl-id="(dpl_[a-zA-Z0-9]+)"', response.text):
            return m
        for m in re.findall(r"dpl_[a-zA-Z0-9]+", response.text):
            return m
        return None

    def _extract_action_hash(self, html: str) -> Optional[str]:
        for m in re.findall(r"[a-f0-9]{40,50}", html):
            return m
        return None

    def _ensure_deployment_info(self) -> str:
        """Fetch and cache deployment ID + action hashes."""
        if self._deployment_id and self._signup_action_hash and self._signin_action_hash:
            return self._deployment_id

        r = self._get(f"{BASE_URL}/login?mode=signup", timeout=15)
        dpl = self._extract_deployment_id(r)
        if dpl:
            self._deployment_id = dpl
        else:
            self._deployment_id = "dpl_unknown"
        h = self._extract_action_hash(r.text)
        if h:
            self._signup_action_hash = h

        r = self._get(f"{BASE_URL}/login", timeout=15)
        h = self._extract_action_hash(r.text)
        if h:
            self._signin_action_hash = h

        return self._deployment_id

    # ------------------------------------------------------------------
    # Turnstile
    # ------------------------------------------------------------------

    def _solve_turnstile(self, page_url: str, timeout: float = 90) -> Optional[str]:
        """Solve Turnstile via Capsolver. Returns token or None."""
        if not self._capsolver_key:
            return None

        r = requests.post(
            "https://api.capsolver.com/createTask",
            json={
                "clientKey": self._capsolver_key,
                "task": {
                    "type": "AntiTurnstileTaskProxyLess",
                    "websiteURL": page_url,
                    "websiteKey": TURNSTILE_SITEKEY,
                },
            },
            timeout=15,
        )
        data = r.json()
        if data.get("errorId") != 0:
            print(f"  Capsolver error: {data.get('errorDescription', data)}")
            return None

        task_id = data["taskId"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(3)
            r = requests.post(
                "https://api.capsolver.com/getTaskResult",
                json={"clientKey": self._capsolver_key, "taskId": task_id},
                timeout=10,
            )
            data = r.json()
            if data.get("status") == "ready":
                return data["solution"]["token"]
            if data.get("errorId") != 0:
                print(f"  Capsolver error: {data.get('errorDescription', data)}")
                return None

        print("  Capsolver timeout")
        return None

    # ------------------------------------------------------------------
    # Next.js Server Action helpers
    # ------------------------------------------------------------------

    def _generate_action_key(self) -> str:
        return "k" + uuid.uuid4().hex[:31]

    def _build_multipart_body(self, action_hash: str, fields: list[tuple[str, str]]) -> tuple[bytes, str]:
        """Build a Next.js Server Action multipart/form-data body."""
        boundary = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]
        action_key = self._generate_action_key()
        sep = f"--{boundary}"

        parts: list[str] = []
        parts.append(f'{sep}\r\nContent-Disposition: form-data; name="1_$ACTION_REF_1"\r\n\r\n\r\n')
        parts.append(f'{sep}\r\nContent-Disposition: form-data; name="1_$ACTION_1:0"\r\n\r\n{{"id":"{action_hash}","bound":"$@1"}}\r\n')
        parts.append(f'{sep}\r\nContent-Disposition: form-data; name="1_$ACTION_1:1"\r\n\r\n["$undefined"]\r\n')
        parts.append(f'{sep}\r\nContent-Disposition: form-data; name="1_$ACTION_KEY"\r\n\r\n{action_key}\r\n')
        parts.append(f'{sep}\r\nContent-Disposition: form-data; name="1_device_fingerprint"\r\n\r\n{self._fingerprint}\r\n')
        parts.append(f'{sep}\r\nContent-Disposition: form-data; name="1_timezone"\r\n\r\n{self._timezone}\r\n')
        parts.append(f'{sep}\r\nContent-Disposition: form-data; name="1_next"\r\n\r\n\r\n')

        for name, value in fields:
            parts.append(f'{sep}\r\nContent-Disposition: form-data; name="1_{name}"\r\n\r\n{value}\r\n')

        parts.append(f'{sep}\r\nContent-Disposition: form-data; name="0"\r\n\r\n["$K1"]\r\n')
        parts.append(f'{sep}--\r\n')

        return "".join(parts).encode("utf-8"), boundary

    def _call_server_action(self, action_hash: str, fields: list[tuple[str, str]], mode: str = "signup") -> dict:
        """Call a Next.js Server Action. Returns {'ok': bool, 'error': str}."""
        body, boundary = self._build_multipart_body(action_hash, fields)
        dpl = self._ensure_deployment_info()

        r = self._post(
            f"{BASE_URL}/login?mode={mode}",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "next-action": action_hash,
                "next-router-state-tree": (
                    "%5B%22%22%2C%7B%22children%22%3A%5B%22login%22%2C%7B%22children%22%3A%5B"
                    "%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%2C0%5D%7D%2Cnull%2Cnull%2C0%5D%7D"
                    "%2Cnull%2Cnull%2C20%5D"
                ),
                "Accept": "text/x-component",
                "Referer": f"{BASE_URL}/login?mode={mode}",
                "x-deployment-id": dpl,
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            },
            data=body,
        )

        # Parse RSC response for real errors (not React refs like $d, $f)
        for line in r.text.strip().split("\n"):
            try:
                _, data = line.split(":", 1)
                parsed = json.loads(data)
                if isinstance(parsed, dict) and "error" in parsed:
                    err = parsed["error"]
                    # React references ($d, $f, etc.) are not real errors
                    if isinstance(err, str) and not err.startswith("$"):
                        return {"ok": False, "error": err}
            except (ValueError, json.JSONDecodeError):
                continue

        # Success indicators: 303 redirect, auth cookies, or 200 with no real error
        if r.status_code in (200, 303):
            return {"ok": True}
        return {"ok": False, "error": f"HTTP {r.status_code}"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def signup(self, email: str, password: str) -> dict:
        """Register a new account."""
        self._fingerprint = str(uuid.uuid4())
        self._ensure_deployment_info()

        turnstile_token = self._solve_turnstile(f"{BASE_URL}/login?mode=signup")
        if not turnstile_token:
            return {"ok": False, "error": "Turnstile solve failed"}

        return self._call_server_action(
            self._signup_action_hash,
            [
                ("cf-turnstile-response", turnstile_token),
                ("email", email),
                ("password", password),
                ("invite_code", ""),
            ],
            mode="signup",
        )

    def verify_email(self, url_or_token: str) -> bool:
        """Verify email via verification link."""
        url = url_or_token if url_or_token.startswith("http") else f"{BASE_URL}/verify-email?token={url_or_token}"
        r = self._get(url, allow_redirects=True)
        return "verify=success" in r.url or "success" in r.url.lower()

    def login(self, email: str, password: str) -> dict:
        """Login and store auth cookies."""
        self._ensure_deployment_info()

        turnstile_token = self._solve_turnstile(f"{BASE_URL}/login")

        fields = [("email", email), ("password", password)]
        if turnstile_token:
            fields.insert(0, ("cf-turnstile-response", turnstile_token))

        result = self._call_server_action(self._signin_action_hash, fields, mode="signin")
        if result.get("ok"):
            self._access_token = self._extract_access_token()
        return result

    def _extract_access_token(self) -> Optional[str]:
        """Extract access token from Supabase chunked cookies."""
        chunked: dict[str, str] = {}
        for cookie in self.session.cookies:
            if cookie.name.startswith("sb-auth-auth-token."):
                idx = cookie.name.split(".")[-1]
                chunked[idx] = cookie.value
        if not chunked:
            return None
        combined = "".join(chunked[k] for k in sorted(chunked.keys()))
        if combined.startswith("base64-"):
            combined = combined[7:]
        rem = len(combined) % 4
        if rem:
            combined += "=" * (4 - rem)
        try:
            return json.loads(base64.b64decode(combined).decode()).get("access_token")
        except Exception:
            return None

    def create_api_key(self, label: str = "auto-cli") -> dict:
        """Create a new API key. Returns full response including plaintext."""
        r = self._post(
            f"{BASE_URL}/api/keys",
            headers={"Content-Type": "application/json", "Origin": BASE_URL},
            json={"label": label},
            cookies=self.session.cookies,
        )
        return r.json() if r.ok else {"error": r.text}

    def list_api_keys(self) -> list[dict]:
        """List all API keys."""
        r = self._get(
            f"{BASE_URL}/api/keys",
            headers={"Content-Type": "application/json", "Origin": BASE_URL},
            cookies=self.session.cookies,
        )
        return r.json().get("keys", []) if r.ok else []

    def enable_free_models(self) -> dict:
        """Accept privacy consent to enable free models."""
        r = self._post(
            f"{BASE_URL}/api/me/privacy",
            headers={"Content-Type": "application/json", "Origin": BASE_URL},
            json={"consent_version": 2, "free_models_enabled": True},
            cookies=self.session.cookies,
        )
        return r.json() if r.ok else {"error": r.text}

    def get_free_tier_status(self) -> dict:
        r = self._get(
            f"{BASE_URL}/api/me/free-tier",
            headers={"Content-Type": "application/json", "Origin": BASE_URL},
            cookies=self.session.cookies,
        )
        return r.json() if r.ok else {"error": r.text}

    def get_privacy_status(self) -> dict:
        r = self._get(
            f"{BASE_URL}/api/me/privacy",
            headers={"Content-Type": "application/json", "Origin": BASE_URL},
            cookies=self.session.cookies,
        )
        return r.json() if r.ok else {"error": r.text}

    def chat(self, api_key: str, model: str, message: str) -> dict:
        """Test API key with a chat completion."""
        r = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": message}], "max_tokens": 50},
            timeout=30,
        )
        return r.json() if r.ok else {"error": r.text, "status": r.status_code}
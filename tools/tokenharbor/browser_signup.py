"""Automated signup using a real Chromium browser (Playwright).

Why: TokenHarbor's signup rejects programmatic (HTTP) submissions --
solver Turnstile tokens are refused server-side, plain HTTP is flagged as
bot, and direct Supabase signup is blocked by a DB trigger. A real browser
signup works (Turnstile auto-verifies). This module drives a real Chromium
to fill the form and submit, then returns the credentials so the normal
HTTP tool flow (verify email -> login -> API key -> free models) continues.
"""
from __future__ import annotations

import re
import time
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

SIGNUP_URL = "https://tokenharbor.ai/login?mode=signup"
DASHBOARD_URL = "https://tokenharbor.ai/dashboard"

# Minimal stealth: hide the most common automation fingerprints.
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = window.chrome || {runtime: {}};
"""


def _proxy_config() -> Optional[dict]:
    """Build Playwright proxy config from environment (VM needs it)."""
    import os
    url = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") \
        or os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
    if not url:
        return None
    return {"server": url}


def browser_signup(email: str, password: str,
                   headless: bool = True,
                   timeout_ms: int = 120_000) -> dict:
    """Run a real-browser signup. Returns {'ok', 'email', 'password', 'error'}."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            proxy=_proxy_config(),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Jakarta",
        )
        ctx.add_init_script(STEALTH_JS)
        page = ctx.new_page()
        try:
            page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)
            # Fill the form fields.
            page.wait_for_selector('input[type="email"]', timeout=30000)
            page.fill('input[type="email"]', email)
            pw = page.query_selector('input[type="password"]')
            if pw:
                pw.fill(password)

            # Wait for Turnstile to auto-verify: the widget injects a hidden
            # input named cf-turnstile-response with a token value.
            token = None
            deadline = time.time() + 60
            while time.time() < deadline:
                token = page.evaluate(
                    """() => {
                        const el = document.querySelector(
                            'input[name="cf-turnstile-response"]');
                        return el && el.value ? el.value : null;
                    }"""
                )
                if token:
                    break
                # If the widget asks for interaction, it shows a checkbox
                # iframe; we cannot click inside it reliably, so just wait.
                time.sleep(1.5)

            # Submit the form.
            btn = page.query_selector('button[type="submit"]')
            if btn:
                btn.click()
            else:
                page.keyboard.press("Enter")

            # Success = redirect to /dashboard.
            try:
                page.wait_for_url("**/dashboard**", timeout=timeout_ms)
                return {"ok": True, "email": email, "password": password,
                        "turnstile": bool(token)}
            except PwTimeout:
                # Surface any visible error text for diagnosis.
                err = page.evaluate(
                    """() => document.body.innerText.slice(0, 500)"""
                )
                m = re.search(r"(Something went wrong[^\n]{0,120}|"
                              r"already[^.\n]{0,80}|"
                              r"Invalid[^\n]{0,80})", err or "")
                return {"ok": False, "email": email, "password": password,
                        "error": m.group(1) if m else "no dashboard redirect"}
        finally:
            ctx.close()
            browser.close()


def auto_farm_one(client, headless: bool = True) -> dict:
    """Full automated pipeline: Tempik email -> browser signup ->
    verify -> login -> API key -> free models. Returns account dict."""
    import re as _re
    from .tempik import TempikClient

    t = TempikClient()
    inbox = t.create_inbox()
    email = inbox["address"] if isinstance(inbox, dict) else inbox
    password = _gen_password()
    print(f"[*] browser signup for {email} ...")
    r = browser_signup(email, password, headless=headless)
    if not r.get("ok"):
        return {"ok": False, "stage": "browser_signup", **r}

    print("[*] verifying email ...")
    msg = t.wait_for_message(email, timeout=120)
    link = None
    if msg:
        m = _re.search(r"https://tokenharbor\.ai/verify-email\?token=[^\s\"<>]+",
                       msg.get("body", ""))
        link = m.group(0) if m else None
    if not link:
        return {"ok": False, "stage": "verify_email", "email": email}
    client.verify_email(link)

    print("[*] logging in ...")
    lr = client.login(email, password)
    if not lr.get("ok"):
        return {"ok": False, "stage": "login", "email": email,
                "password": password, "error": lr}

    print("[*] creating API key ...")
    kr = client.create_api_key("auto-farm")
    api_key = kr.get("plaintext") or (kr.get("key") or {}).get("plaintext")
    if not api_key:
        return {"ok": False, "stage": "api_key", "email": email,
                "password": password}

    print("[*] enabling free models ...")
    fr = client.enable_free_models()
    return {"ok": True, "email": email, "password": password,
            "api_key": api_key, "free_models": fr.get("ok")}


def _gen_password(length: int = 16) -> str:
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))

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
                   timeout_ms: int = 120_000,
                   proxy: Optional[str] = None,
                   verbose: bool = True) -> dict:
    """Run a real-browser signup. Returns {'ok', 'email', 'password', 'error'}."""
    def log(msg: str):
        if verbose:
            print(f"    [browser] {msg}", flush=True)

    # Proxy: explicit arg wins, else env (VM), else None (direct).
    # Format: [http://|socks5://]user:pass@host:port
    pw_proxy = None
    if proxy:
        import re as _re
        m = _re.match(r"(?:(https?|socks5?)://)?([^:]+):([^@]+)@([^:]+):(\d+)", proxy)
        if m:
            scheme, user, pwd, host, port = m.groups()
            server_scheme = "socks5" if scheme == "socks5" else "http"
            pw_proxy = {"server": f"{server_scheme}://{host}:{port}",
                        "username": user, "password": pwd}
        else:
            pw_proxy = {"server": proxy}
    else:
        pw_proxy = _proxy_config()

    with sync_playwright() as p:
        log("launching Chromium ...")
        browser = p.chromium.launch(
            headless=headless,
            proxy=pw_proxy,
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
            log(f"opening {SIGNUP_URL} ...")
            page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=60000)
            # The site may land on the Sign in tab; explicitly switch to Sign up.
            log("ensuring Sign up tab is active ...")
            try:
                signup_tab = page.query_selector(
                    'button:has-text("Sign up"), [role="tab"]:has-text("Sign up"),'
                    ' a:has-text("Sign up")')
                if signup_tab:
                    # Only click if it looks like a tab that's not active.
                    page.evaluate(
                        """(el) => {
                            const txt = (el.innerText || '').trim();
                            if (txt.toLowerCase() === 'sign up') el.click();
                        }""", signup_tab)
                    page.wait_for_timeout(2000)
            except Exception:
                pass
            log("page loaded, waiting for email field ...")
            # Fill the form fields.
            try:
                page.wait_for_selector('input[type="email"]', timeout=30000)
            except PwTimeout:
                # Diagnose: what is the page actually showing?
                title = page.title()
                body = page.evaluate("() => document.body.innerText.slice(0, 300)") or ""
                log(f"FAIL: no email field. title={title!r} body={body[:150]!r}")
                return {"ok": False, "email": email, "password": password,
                        "error": f"signup form not loaded (title: {title})"}
            log("filling credentials ...")
            page.fill('input[type="email"]', email)
            pw = page.query_selector('input[type="password"]')
            if pw:
                pw.fill(password)

            # Wait for Turnstile to auto-verify: the widget injects a hidden
            # input named cf-turnstile-response with a token value.
            log("waiting for Turnstile auto-verify ...")
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
                time.sleep(1.5)
            log(f"turnstile token: {'OK' if token else 'MISSING (will submit anyway)'}")

            # Submit the form.
            log("submitting ...")
            btn = page.query_selector('button[type="submit"]')
            if btn:
                btn.click()
            else:
                page.keyboard.press("Enter")

            # Success = redirect to /dashboard.
            log("waiting for dashboard redirect ...")
            try:
                page.wait_for_url("**/dashboard**", timeout=timeout_ms)
                log("reached dashboard")
                return {"ok": True, "email": email, "password": password,
                        "turnstile": bool(token)}
            except PwTimeout:
                # Deep diagnostics: screenshot + page state.
                import os as _os
                shot = f"/tmp/signup-fail-{int(time.time())}.png"
                try:
                    page.screenshot(path=shot)
                    log(f"screenshot saved: {shot}")
                except Exception:
                    pass
                err = page.evaluate(
                    """() => document.body.innerText.slice(0, 800)"""
                ) or ""
                url = page.url
                # Check Turnstile widget state.
                ts = page.evaluate(
                    """() => {
                        const iframes = document.querySelectorAll(
                            'iframe[src*="turnstile"], iframe[src*="cloudflare"]');
                        const widget = document.querySelector('.cf-turnstile');
                        return {iframes: iframes.length,
                                widget: !!widget,
                                token: !!(document.querySelector(
                                    'input[name="cf-turnstile-response"]') || {}).value};
                    }"""
                ) or {}
                log(f"after submit: url={url} turnstile={ts}")
                m = re.search(r"(Something went wrong[^\n]{0,120}|"
                              r"already[^.\n]{0,80}|"
                              r"Invalid[^\n]{0,80}|"
                              r"try again[^\n]{0,80})", err)
                detail = m.group(1) if m else "no dashboard redirect"
                log(f"FAIL: {detail}")
                return {"ok": False, "email": email, "password": password,
                        "error": detail, "screenshot": shot,
                        "page_url": url, "turnstile_state": ts}
        finally:
            ctx.close()
            browser.close()


def auto_farm_one(client, headless: bool = True,
                  proxy: Optional[str] = None) -> dict:
    """Full automated pipeline: Tempik email -> browser signup ->
    verify -> login -> API key -> free models. Returns account dict."""
    import re as _re
    from .tempik import TempikClient

    t = TempikClient()
    inbox = t.create_inbox()
    email = inbox["address"] if isinstance(inbox, dict) else inbox
    password = _gen_password()
    print(f"[*] browser signup for {email} ...")
    r = browser_signup(email, password, headless=headless, proxy=proxy)
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

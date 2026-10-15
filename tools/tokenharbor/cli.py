#!/usr/bin/env python3
"""
TokenHarbor Auto CLI — Interactive terminal tool with Rich UI.
HTTP mode, no browser needed.

Usage:
  python3 -m tools.tokenharbor.cli              # interactive menu
  python3 -m tools.tokenharbor.cli full-setup    # one-shot full flow
  python3 -m tools.tokenharbor.cli batch 5       # batch create 5 accounts
  python3 -m tools.tokenharbor.cli test-key THK  # test single key
"""

from __future__ import annotations

import json
import random
import re
import secrets
import string
import sys
import time
import tomllib
from pathlib import Path
from typing import Optional

# ── path setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
TOOLS_DIR = PROJECT_ROOT / "tools"

# ── config ──────────────────────────────────────────────────────────────────
_CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"
with open(_CONFIG_PATH, "rb") as _f:
    _cfg = tomllib.load(_f)

_TH_BASE_URL = _cfg["tokenharbor"]["base_url"]
_CAPSOLVER_KEY_FILE = PROJECT_ROOT / _cfg["files"]["capsolver_key"]
_PROXY_FILE = PROJECT_ROOT / _cfg["files"]["proxy_list"]
_ACCOUNT_FILE = _cfg["files"]["account_output"]
_FREE_MODELS = _cfg["models"]["free"]

# ── rich ────────────────────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt, Confirm, IntPrompt
from rich import box

console = Console()

# ── local imports ───────────────────────────────────────────────────────────
from tools.tokenharbor.client import TokenHarborClient
from tools.tokenharbor.tempik import TempikClient

# ═══════════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════════

# cached domain list from Tempik
_DOMAINS_CACHE: Optional[list[str]] = None


def _load_capsolver_key() -> Optional[str]:
    if _CAPSOLVER_KEY_FILE.exists():
        return _CAPSOLVER_KEY_FILE.read_text().strip()
    return None


def _load_random_proxy() -> Optional[str]:
    if _PROXY_FILE.exists():
        lines = [l.strip() for l in _PROXY_FILE.read_text().strip().split("\n") if l.strip()]
        if lines:
            raw = random.choice(lines)
            creds = raw.split("\t")[-1]
            return "http://" + creds
    return None


def _load_all_proxies() -> list[str]:
    """Load all proxies from file."""
    if _PROXY_FILE.exists():
        lines = [l.strip() for l in _PROXY_FILE.read_text().strip().split("\n") if l.strip()]
        return ["http://" + l.split("\t")[-1] for l in lines]
    return []


def _check_proxy(proxy: str, timeout: float = 8) -> bool:
    """Test if a proxy is alive by hitting tokenharbor.ai."""
    import requests as _r
    try:
        resp = _r.get(
            f"{_TH_BASE_URL}/login",
            proxies={"http": proxy, "https": proxy},
            timeout=timeout,
        )
        return resp.status_code < 500
    except Exception:
        return False


def _check_all_proxies(proxies: Optional[list[str]] = None, timeout: float = 8) -> tuple[list[str], list[str]]:
    """Check all proxies. Returns (alive, dead)."""
    if proxies is None:
        proxies = _load_all_proxies()
    alive, dead = [], []
    for p in proxies:
        if _check_proxy(p, timeout=timeout):
            alive.append(p)
        else:
            dead.append(p)
    return alive, dead


def _get_working_proxy(checked_alive: Optional[list[str]] = None) -> Optional[str]:
    """Get a random working proxy. If checked_alive provided, use it; otherwise check one on the fly."""
    if checked_alive:
        return random.choice(checked_alive)
    return _load_random_proxy()


def _pick_working_proxy_interactive() -> Optional[str]:
    """Interactive: check proxies and pick a working one. Returns proxy URL or None."""
    all_proxies = _load_all_proxies()
    if not all_proxies:
        console.print("[yellow]No proxies found in proxy file[/yellow]")
        return None

    console.print(f"[bold cyan]Checking {len(all_proxies)} proxies...[/bold cyan]")
    alive, dead = _check_all_proxies(all_proxies)
    if not alive:
        console.print(f"[red]✗ All {len(dead)} proxies are dead![/red]")
        return None

    console.print(f"  [green]✓ {len(alive)} alive[/green]  [red]✗ {len(dead)} dead[/red]")
    return random.choice(alive)


def _gen_password(length: int = 20) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(chars) for _ in range(length))


def _get_domains() -> list[str]:
    """Fetch available Tempik domains (cached). Falls back to exse7en.fr."""
    global _DOMAINS_CACHE
    if _DOMAINS_CACHE is None:
        try:
            tempik = TempikClient()
            _DOMAINS_CACHE = tempik.get_domains()
        except Exception:
            _DOMAINS_CACHE = ["exse7en.fr"]
    return _DOMAINS_CACHE


def _gen_email(domain: Optional[str] = None) -> str:
    """Generate random email with random Tempik domain."""
    local_part = "th_" + "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10)
    )
    if domain is None:
        domain = random.choice(_get_domains())
    return f"{local_part}@{domain}"


def _save_account(account: dict, path: Optional[str] = None) -> None:
    filepath = Path(path or _ACCOUNT_FILE)
    if filepath.exists():
        try:
            existing = json.loads(filepath.read_text())
        except json.JSONDecodeError:
            existing = []
        if isinstance(existing, list):
            existing.append(account)
        else:
            existing = [existing, account]
        filepath.write_text(json.dumps(existing, indent=2))
    else:
        filepath.write_text(json.dumps(account, indent=2))


# ═══════════════════════════════════════════════════════════════════════════════
# banner
# ═══════════════════════════════════════════════════════════════════════════════

BANNER = r"""
[bold cyan]
               ██╗  ██╗ █████╗ ██████╗ ██████╗  ██████╗ ██████╗
               ██║  ██║██╔══██╗██╔══██╗██╔══██╗██╔═══██╗██╔══██╗
               ███████║███████║██████╔╝██████╔╝██║   ██║██████╔╝
               ██╔══██║██╔══██║██╔══██╗██╔══██╗██║   ██║██╔══██╗
               ██║  ██║██║  ██║██║  ██║██████╔╝╚██████╔╝██║  ██║
               ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝
[/bold cyan]
[bold bright_cyan]                 TokenHarbor Auto CLI — HTTP Mode • No Browser[/bold bright_cyan]
[dim italic]                                 by MASANTOID[/dim italic]
"""


def _print_banner(clear: bool = True):
    if clear:
        console.clear()
    console.print(BANNER)
    console.print()


# ═══════════════════════════════════════════════════════════════════════════════
# single account setup
# ═══════════════════════════════════════════════════════════════════════════════

def _run_single_setup(
    email: str,
    password: str,
    capsolver_key: str,
    proxy: Optional[str] = None,
    progress: Optional[Progress] = None,
    parent_task: Optional[int] = None,
) -> Optional[dict]:
    """
    Run full setup for ONE account. Returns account dict or None.
    If progress/parent_task are passed, updates inside that progress tree (batch mode).
    """
    proxy = proxy or _load_random_proxy()
    client = TokenHarborClient(capsolver_key=capsolver_key, proxy=proxy)

    # ── step 1: signup ──────────────────────────────────────────────────
    if progress and parent_task is not None:
        progress.update(parent_task, description=f"[cyan]Signup: {email}[/cyan]")
    result = client.signup(email, password)
    if not result.get("ok"):
        if progress:
            console.print(f"  [red]✗ Signup failed:[/red] {result.get('error')}")
        return None

    # ── step 2: wait for verification email ─────────────────────────────
    if progress and parent_task is not None:
        progress.update(parent_task, description=f"[cyan]Waiting email: {email}[/cyan]")
    tempik = TempikClient()
    local_part = email.split("@")[0]
    domain = email.split("@")[1]
    tempik.create_inbox(local_part=local_part, domain=domain)

    verification_link = None
    for _ in range(24):  # up to 120s with 5s intervals
        msg = tempik.wait_for_message(email, timeout=5)
        if msg:
            body = msg.get("body", "")
            match = re.search(r"https://tokenharbor\.ai/verify-email\?token=[^\s\"<>]+", body)
            if match:
                verification_link = match.group()
                break
    if not verification_link:
        if progress:
            console.print(f"  [red]✗ No verification email for {email}[/red]")
        return None

    # ── step 3: verify email ────────────────────────────────────────────
    if progress and parent_task is not None:
        progress.update(parent_task, description=f"[cyan]Verify: {email}[/cyan]")
    client.verify_email(verification_link)

    # ── step 4: login ───────────────────────────────────────────────────
    if progress and parent_task is not None:
        progress.update(parent_task, description=f"[cyan]Login: {email}[/cyan]")
    login_result = client.login(email, password)
    if not login_result.get("ok"):
        if progress:
            console.print(f"  [red]✗ Login failed for {email}:[/red] {login_result.get('error')}")
        return None

    # ── step 5: create API key ──────────────────────────────────────────
    if progress and parent_task is not None:
        progress.update(parent_task, description=f"[cyan]Key: {email}[/cyan]")
    key_result = client.create_api_key("auto-cli")
    api_key = key_result.get("plaintext") or key_result.get("key", {}).get("plaintext")
    if not api_key:
        if progress:
            console.print(f"  [red]✗ API key failed for {email}[/red]")
        return None

    # ── step 6: enable free models ──────────────────────────────────────
    if progress and parent_task is not None:
        progress.update(parent_task, description=f"[cyan]Free models: {email}[/cyan]")
    free_result = client.enable_free_models()
    free_enabled = free_result.get("ok") or free_result.get("free_models_enabled")

    return {
        "email": email,
        "password": password,
        "api_key": api_key,
        "free_tier_enabled": bool(free_enabled),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _run_full_setup(email: Optional[str] = None, password: Optional[str] = None) -> int:
    """Complete flow: register → verify → login → create key → enable free → test."""
    email = email or _gen_email()
    password = password or _gen_password()

    _print_banner()

    domains = _get_domains()
    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan", justify="right")
    info.add_column(style="white")
    info.add_row("Email    ", email)
    info.add_row("Password ", password)
    info.add_row("Domains  ", ", ".join(domains))
    console.print(Panel(info, title="[bold]Account Info[/bold]", border_style="cyan"))

    capsolver_key = _load_capsolver_key()
    if not capsolver_key:
        console.print(f"[red]✗ Capsolver key not found at {_CAPSOLVER_KEY_FILE}[/red]")
        return 1

    # check & pick working proxy
    proxy = _pick_working_proxy_interactive()
    if proxy is None:
        console.print("[red]✗ No working proxy available[/red]")
        return 1

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Setup...", total=6)

        progress.update(task, description="[cyan]Signing up...")
        account = _run_single_setup(email, password, capsolver_key, proxy=proxy, progress=progress, parent_task=task)
        if account is None:
            progress.stop()
            return 1
        progress.update(task, completed=6)

    # ── test ────────────────────────────────────────────────────────────
    api_key = account["api_key"]
    free_enabled = account["free_tier_enabled"]
    console.print()
    console.print("[bold cyan]Testing API key...[/bold cyan]")
    client = TokenHarborClient(capsolver_key=capsolver_key, proxy=_load_random_proxy())
    test = client.chat(api_key, _FREE_MODELS[0], "Say 'TokenHarbor CLI works!' in 5 words")
    if "choices" in test:
        content = test["choices"][0]["message"]["content"]
        console.print(f"  [green]✓[/green] {content}")
    else:
        console.print(f"  [yellow]⚠[/yellow] {test.get('error', test)}")

    # ── save ────────────────────────────────────────────────────────────
    _save_account(account)

    # ── result ──────────────────────────────────────────────────────────
    rt = Table.grid(padding=(0, 2))
    rt.add_column(style="bold cyan", justify="right")
    rt.add_column(style="white")
    rt.add_row("Email              ", email)
    rt.add_row("Password           ", password)
    rt.add_row("API Key            ", f"[bold green]{api_key}[/bold green]")
    rt.add_row("Free Tier Enabled  ", "✓" if free_enabled else "✗")
    console.print()
    console.print(Panel(rt, title="[bold green]✓ Setup Complete[/bold green]", border_style="green"))
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# batch mode
# ═══════════════════════════════════════════════════════════════════════════════

def _run_batch(count: int) -> int:
    """Create N accounts in batch mode."""
    _print_banner()

    capsolver_key = _load_capsolver_key()
    if not capsolver_key:
        console.print(f"[red]✗ Capsolver key not found at {_CAPSOLVER_KEY_FILE}[/red]")
        return 1

    domains = _get_domains()
    console.print(f"  [dim]Domains:[/dim] {', '.join(domains)}")
    console.print(f"  [dim]Accounts to create:[/dim] {count}")
    console.print()

    # pre-check all proxies
    console.print("[bold cyan]Checking proxies...[/bold cyan]")
    all_proxies = _load_all_proxies()
    alive, dead = _check_all_proxies(all_proxies)
    if not alive:
        console.print(f"[red]✗ All {len(dead)} proxies are dead![/red]")
        return 1
    console.print(f"  [green]✓ {len(alive)} alive[/green]  [red]✗ {len(dead)} dead[/red]")
    console.print()

    accounts: list[dict] = []
    failed = 0
    working = list(alive)  # copy to rotate through

    for i in range(1, count + 1):
        domain = random.choice(domains)
        email = _gen_email(domain=domain)
        password = _gen_password()
        proxy = random.choice(working)

        console.print(f"[bold]── [{i}/{count}][/bold] {email} [dim]({domain})[/dim]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Working...", total=6)
            account = _run_single_setup(email, password, capsolver_key, proxy=proxy, progress=progress, parent_task=task)
            if account is None:
                failed += 1
                progress.update(task, completed=6)
            else:
                accounts.append(account)
                _save_account(account)
                progress.update(task, completed=6, description="[green]✓ Done[/green]")

        # small delay between accounts to avoid rate limiting
        if i < count:
            time.sleep(2)

    # ── summary ─────────────────────────────────────────────────────────
    console.print()
    summary = Table(title="[bold]Batch Summary[/bold]", box=box.ROUNDED, border_style="cyan")
    summary.add_column("#", style="dim")
    summary.add_column("Email", style="cyan")
    summary.add_column("API Key", style="green")
    summary.add_column("Free", style="bold")
    for j, a in enumerate(accounts, 1):
        key = a["api_key"]
        summary.add_row(
            str(j),
            a["email"],
            key[:30] + "..." if len(key) > 30 else key,
            "✓" if a.get("free_tier_enabled") else "✗",
        )

    if failed > 0:
        summary.add_row("", f"[red]{failed} failed[/red]", "", "")

    console.print(summary)
    console.print(f"[bold green]✓ {len(accounts)}/{count} accounts created[/bold green]")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# other commands
# ═══════════════════════════════════════════════════════════════════════════════

def _run_create_key(email: str, password: str, label: str = "auto-cli") -> int:
    _print_banner()
    capsolver_key = _load_capsolver_key()
    if not capsolver_key:
        console.print("[red]✗ Capsolver key not found[/red]")
        return 1

    proxy = _load_random_proxy()
    console.print(f"  [dim]Proxy:[/dim] {proxy or '[yellow]none[/yellow]'}")
    client = TokenHarborClient(capsolver_key=capsolver_key, proxy=proxy)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]Logging in...", total=None)
        login_result = client.login(email, password)
        if not login_result.get("ok"):
            progress.stop()
            console.print(f"[red]✗ Login failed:[/red] {login_result.get('error')}")
            return 1

        progress.update(task, description="[cyan]Creating API key...")
        key_result = client.create_api_key(label)
        api_key = key_result.get("plaintext") or key_result.get("key", {}).get("plaintext")

    if api_key:
        _save_account({"email": email, "api_key": api_key, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        console.print()
        console.print(Panel(f"[bold green]{api_key}[/bold green]", title="[bold]API Key Created[/bold]", border_style="green"))
        return 0

    console.print(f"[red]✗ Failed:[/red] {json.dumps(key_result)[:200]}")
    return 1


def _run_check_proxies() -> int:
    """Check all proxies and display results."""
    _print_banner()
    all_proxies = _load_all_proxies()
    if not all_proxies:
        console.print("[yellow]No proxies found in proxy file[/yellow]")
        return 1

    console.print(f"[bold cyan]Checking {len(all_proxies)} proxies...[/bold cyan]")
    console.print()

    alive, dead = _check_all_proxies(all_proxies)

    table = Table(title="[bold]Proxy Check Results[/bold]", box=box.ROUNDED, border_style="cyan")
    table.add_column("Proxy", style="dim")
    table.add_column("Status", style="bold")

    for p in alive:
        table.add_row(p, "[green]✓ Alive[/green]")
    for p in dead:
        table.add_row(p, "[red]✗ Dead[/red]")

    console.print(table)
    console.print()
    console.print(f"  [green]✓ {len(alive)} alive[/green]  │  [red]✗ {len(dead)} dead[/red]  │  Total: {len(all_proxies)}")
    return 0


def _run_test_key(key: str) -> int:
    _print_banner()
    import requests

    table = Table(title="[bold]API Key Test[/bold]", box=box.ROUNDED, border_style="cyan")
    table.add_column("Model", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Response", style="dim")

    for model_id in _FREE_MODELS:
        with Progress(SpinnerColumn(), TextColumn(f"[dim]Testing {model_id}...[/dim]"), console=console) as progress:
            t = progress.add_task("", total=None)
            try:
                r = requests.post(
                    f"{_TH_BASE_URL}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model_id, "messages": [{"role": "user", "content": "Say hi in 3 words"}], "max_tokens": 20},
                    timeout=30,
                )
                if r.ok:
                    content = r.json()["choices"][0]["message"]["content"]
                    table.add_row(model_id, "[green]✓ OK[/green]", content)
                else:
                    table.add_row(model_id, f"[red]✗ {r.status_code}[/red]", r.text[:100])
            except Exception as e:
                table.add_row(model_id, "[red]✗ Error[/red]", str(e)[:80])
            progress.remove_task(t)

    console.print(table)
    return 0


def _run_enable_free(email: str, password: str) -> int:
    _print_banner()
    capsolver_key = _load_capsolver_key()
    proxy = _load_random_proxy()
    console.print(f"  [dim]Proxy:[/dim] {proxy or '[yellow]none[/yellow]'}")
    client = TokenHarborClient(capsolver_key=capsolver_key, proxy=proxy)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]Logging in...", total=None)
        login_result = client.login(email, password)
        if not login_result.get("ok"):
            progress.stop()
            console.print(f"[red]✗ Login failed:[/red] {login_result.get('error')}")
            return 1

        progress.update(task, description="[cyan]Enabling free models...")
        result = client.enable_free_models()

    if result.get("ok"):
        console.print("[green]✓ Free models enabled![/green]")
        return 0
    console.print(f"[red]✗ Failed:[/red] {json.dumps(result)[:200]}")
    return 1


def _run_status(email: str, password: str) -> int:
    _print_banner()
    capsolver_key = _load_capsolver_key()
    proxy = _load_random_proxy()
    console.print(f"  [dim]Proxy:[/dim] {proxy or '[yellow]none[/yellow]'}")
    client = TokenHarborClient(capsolver_key=capsolver_key, proxy=proxy)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("[cyan]Logging in...", total=None)
        login_result = client.login(email, password)
        if not login_result.get("ok"):
            progress.stop()
            console.print(f"[red]✗ Login failed:[/red] {login_result.get('error')}")
            return 1

        progress.update(task, description="[cyan]Fetching status...")
        free_tier = client.get_free_tier_status()
        privacy = client.get_privacy_status()
        keys = client.list_api_keys()

    ft = Table(title="[bold]Free Tier[/bold]", box=box.SIMPLE, border_style="cyan")
    ft.add_column("Key", style="cyan"); ft.add_column("Value")
    for k, v in free_tier.items():
        ft.add_row(str(k), str(v))
    console.print(ft)

    console.print()
    pv = Table(title="[bold]Privacy[/bold]", box=box.SIMPLE, border_style="cyan")
    pv.add_column("Key", style="cyan"); pv.add_column("Value")
    for k, v in privacy.items():
        pv.add_row(str(k), str(v))
    console.print(pv)

    console.print()
    kt = Table(title="[bold]API Keys[/bold]", box=box.SIMPLE, border_style="cyan")
    kt.add_column("Label", style="cyan"); kt.add_column("Prefix", style="dim"); kt.add_column("Created", style="dim")
    for k in keys:
        prefix = k.get("prefix", "?")
        kt.add_row(k.get("label", "?"), prefix[:20] + "..." if len(prefix) > 20 else prefix, k.get("created_at", "?"))
    console.print(kt)
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# interactive menu
# ═══════════════════════════════════════════════════════════════════════════════

def _interactive_menu() -> int:
    while True:
        console.clear()
        _print_banner()

        capsolver_key = _load_capsolver_key()
        proxy = _load_random_proxy()
        domains = _get_domains()

        # status box
        status_grid = Table.grid(padding=(0, 3))
        status_grid.add_column(justify="center")
        status_grid.add_column(justify="center")
        status_grid.add_column(justify="center")
        caps_status = "[green]✓ Capsolver ready[/green]" if capsolver_key else "[red]✗ Capsolver missing[/red]"
        proxy_status = "[green]✓ Proxy ready[/green]" if proxy else "[yellow]⚠ Proxy none[/yellow]"
        domain_status = f"[dim]📧 {', '.join(domains)}[/dim]"
        status_grid.add_row(caps_status, proxy_status, domain_status)
        console.print(Panel(status_grid, border_style="dim cyan", padding=(0, 2)))
        console.print()

        menu = Table(show_header=False, box=box.SIMPLE, padding=(0, 3))
        menu.add_column("Key", style="bold cyan", width=4)
        menu.add_column("Command", style="white")
        menu.add_column("Description", style="dim")
        menu.add_row("[1]", "Full Setup",       "Register → Verify → Login → API Key → Free Models → Test")
        menu.add_row("[2]", "Batch Create",     "Create multiple accounts at once")
        menu.add_row("[3]", "Create API Key",   "Login with existing account and create a new API key")
        menu.add_row("[4]", "Test API Key",     "Test an API key against all free models")
        menu.add_row("[5]", "Enable Free",      "Enable free models for an existing account")
        menu.add_row("[6]", "Account Status",   "Check free tier, privacy, and API keys")
        menu.add_row("[7]", "Check Proxies",    "Test all proxies and show alive/dead")
        menu.add_row("[8]", "List Accounts",    "Show saved accounts from account.json")
        menu.add_row("[q]", "Quit",             "Exit the CLI")
        console.print(Panel(menu, title="[bold]Menu[/bold]", border_style="cyan"))

        console.print()
        choice = Prompt.ask("[bold cyan]Select[/bold cyan]", choices=["1", "2", "3", "4", "5", "6", "7", "8", "q"], default="1")

        if choice == "q":
            console.print("[dim]Bye![/dim]")
            return 0

        elif choice == "1":
            console.clear()
            use_custom = Confirm.ask("Use custom email/password?", default=False)
            email, password = None, None
            if use_custom:
                email = Prompt.ask("Email", default=_gen_email())
                password = Prompt.ask("Password", default=_gen_password())
            _run_full_setup(email=email, password=password)
            console.print(); input("Press Enter to continue...")

        elif choice == "2":
            console.clear()
            count = IntPrompt.ask("How many accounts?", default=3)
            _run_batch(count)
            console.print(); input("Press Enter to continue...")

        elif choice == "3":
            console.clear()
            email = Prompt.ask("Email")
            password = Prompt.ask("Password", password=True)
            label = Prompt.ask("Key label", default="auto-cli")
            _run_create_key(email, password, label)
            console.print(); input("Press Enter to continue...")

        elif choice == "4":
            console.clear()
            key = Prompt.ask("API Key")
            _run_test_key(key)
            console.print(); input("Press Enter to continue...")

        elif choice == "5":
            console.clear()
            email = Prompt.ask("Email")
            password = Prompt.ask("Password", password=True)
            _run_enable_free(email, password)
            console.print(); input("Press Enter to continue...")

        elif choice == "6":
            console.clear()
            email = Prompt.ask("Email")
            password = Prompt.ask("Password", password=True)
            _run_status(email, password)
            console.print(); input("Press Enter to continue...")

        elif choice == "7":
            console.clear()
            _run_check_proxies()
            console.print(); input("Press Enter to continue...")

        elif choice == "8":
            console.clear()
            _print_banner()
            acct_file = Path(_ACCOUNT_FILE)
            if acct_file.exists():
                try:
                    accounts = json.loads(acct_file.read_text())
                    if not isinstance(accounts, list):
                        accounts = [accounts]
                    tbl = Table(title="[bold]Saved Accounts[/bold]", box=box.ROUNDED, border_style="cyan")
                    tbl.add_column("#", style="dim")
                    tbl.add_column("Email", style="cyan")
                    tbl.add_column("API Key", style="green")
                    tbl.add_column("Free", style="bold")
                    tbl.add_column("Created", style="dim")
                    for i, a in enumerate(accounts, 1):
                        key = a.get("api_key", "?")
                        if len(key) > 30:
                            key = key[:30] + "..."
                        tbl.add_row(str(i), a.get("email", "?"), key,
                                    "✓" if a.get("free_tier_enabled") else "✗", a.get("created_at", "?"))
                    console.print(tbl)
                except json.JSONDecodeError:
                    console.print("[yellow]account.json is corrupted[/yellow]")
            else:
                console.print("[dim]No accounts saved yet.[/dim]")
            console.print(); input("Press Enter to continue...")


# ═══════════════════════════════════════════════════════════════════════════════
# argparse
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="TokenHarbor Auto CLI")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("full-setup")
    p.add_argument("--email"); p.add_argument("--password")

    p = sub.add_parser("batch")
    p.add_argument("count", type=int, help="Number of accounts to create")

    p = sub.add_parser("create-key")
    p.add_argument("--email", required=True); p.add_argument("--password", required=True)
    p.add_argument("--label", default="auto-cli")

    p = sub.add_parser("test-key")
    p.add_argument("key")

    p = sub.add_parser("enable-free")
    p.add_argument("--email", required=True); p.add_argument("--password", required=True)

    p = sub.add_parser("check-proxies", help="Check all proxies")
    p = sub.add_parser("status")
    p.add_argument("--email", required=True); p.add_argument("--password", required=True)

    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    args = _parse_args()

    if args.command == "full-setup":
        return _run_full_setup(email=args.email, password=args.password)
    elif args.command == "batch":
        return _run_batch(args.count)
    elif args.command == "create-key":
        return _run_create_key(args.email, args.password, args.label)
    elif args.command == "test-key":
        return _run_test_key(args.key)
    elif args.command == "enable-free":
        return _run_enable_free(args.email, args.password)
    elif args.command == "check-proxies":
        return _run_check_proxies()
    elif args.command == "status":
        return _run_status(args.email, args.password)
    else:
        return _interactive_menu()


if __name__ == "__main__":
    sys.exit(main())
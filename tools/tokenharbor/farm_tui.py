"""Interactive TUI for TokenHarbor + Mistral farming.

Launched via the `farm` command after running install.sh.
Main menu: Farm TokenHarbor | Farm Mistral keys | Parallel farm |
           Delay setting | Setup Proxy
Each farm has its own submenu with Run farm / Results.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table

console = Console()

REPO_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"
PROXY_PATH = REPO_DIR / "tools" / "proxies.txt"
CAPSOLVER_PATH = Path(__file__).resolve().parent / ".capsolver_key"
RESULTS_PATH = REPO_DIR / "account.json"
TUI_STATE = Path.home() / ".farm_tui.json"

MISTRAL_SCRIPT = Path("/root/mistral_farm.py")
MISTRAL_KEYS = Path("/root/mistral_keys.txt")
DAHL_SCRIPT = Path("/root/dahl_farm.py")
DAHL_KEYS = Path("/root/dahl_keys.txt")

DEFAULT_DELAY = 60


def _load_state() -> dict:
    if TUI_STATE.exists():
        try:
            return json.loads(TUI_STATE.read_text())
        except json.JSONDecodeError:
            pass
    return {"delay": DEFAULT_DELAY, "mistral_auto_inject": False}


def _save_state(state: dict) -> None:
    TUI_STATE.write_text(json.dumps(state, indent=2))


def _get_tempik_url() -> str | None:
    if not CONFIG_PATH.exists():
        return None
    try:
        import tomllib
        with open(CONFIG_PATH, "rb") as f:
            cfg = tomllib.load(f)
        url = cfg.get("tempik", {}).get("base_url", "")
        return url or None
    except Exception:
        return None


def _set_tempik_url(url: str) -> None:
    import tomllib
    cfg = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            cfg = tomllib.load(f)
    cfg.setdefault("tokenharbor", {})["base_url"] = "https://tokenharbor.ai"
    cfg.setdefault("tokenharbor", {})["turnstile_sitekey"] = "0x4AAAAAADBuC8Knz1EJZx9-"
    cfg.setdefault("tempik", {})["base_url"] = url
    files = cfg.setdefault("files", {})
    files.setdefault("capsolver_key", "tools/.capsolver_key")
    files.setdefault("proxy_list", "tools/proxies.txt")
    files.setdefault("account_output", "account.json")
    cfg.setdefault("models", {})["free"] = [
        "deepseek-v4-flash:free",
        "mimo-v2.5:free",
        "qwen3.8-27b:free",
    ]
    # Write back as TOML manually (no writer dep).
    lines = []
    for section, vals in cfg.items():
        lines.append(f"[{section}]")
        for k, v in vals.items():
            if isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, list):
                items = ", ".join(f'"{x}"' for x in v)
                lines.append(f"{k} = [{items}]")
            else:
                lines.append(f"{k} = {v}")
        lines.append("")
    CONFIG_PATH.write_text("\n".join(lines))


def _get_proxies() -> list:
    """Return all configured proxies (one per line)."""
    if PROXY_PATH.exists():
        lines = PROXY_PATH.read_text().strip().splitlines()
        return [x.strip() for x in lines
                if x.strip() and not x.strip().startswith("#")]
    return []


def _get_proxy() -> str | None:
    proxies = _get_proxies()
    return proxies[0] if proxies else None


def _set_proxies(proxies: list) -> None:
    PROXY_PATH.write_text("\n".join(p.strip() for p in proxies if p.strip()) + "\n")


def _clear_screen():
    console.clear()


def _gradient_text(text: str, stops: list) -> "Text":
    """Apply horizontal gradient across text. stops = [(pos, (r,g,b)), ...]."""
    from rich.text import Text
    out = Text()
    chars = list(text)
    n = len(chars)
    for i, ch in enumerate(chars):
        t = i / max(n - 1, 1)
        # Find surrounding stops.
        for s in range(len(stops) - 1):
            p0, c0 = stops[s]
            p1, c1 = stops[s + 1]
            if p0 <= t <= p1:
                f = (t - p0) / max(p1 - p0, 1e-9)
                r = int(c0[0] + (c1[0] - c0[0]) * f)
                g = int(c0[1] + (c1[1] - c0[1]) * f)
                b = int(c0[2] + (c1[2] - c0[2]) * f)
                break
        else:
            r, g, b = stops[-1][1]
        if ch == " ":
            out.append(ch)
        else:
            out.append(ch, style=f"bold #{r:02x}{g:02x}{b:02x}")
    return out


FARM_ART = [
    "███████╗ █████╗ ██████╗ ███╗   ███╗",
    "██╔════╝██╔══██╗██╔══██╗████╗ ████║",
    "█████╗  ███████║██████╔╝██╔████╔██║",
    "██╔══╝  ██╔══██║██╔══██╗██║╚██╔╝██║",
    "██║     ██║  ██║██║  ██║██║ ╚═╝ ██║",
    "╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝",
]
# Orange -> pink -> purple (like the KEDAI VPN photo).
FARM_GRADIENT = [
    (0.0, (255, 165, 0)),    # orange
    (0.5, (255, 20, 147)),    # pink
    (1.0, (148, 0, 211)),     # purple
]
FARM_INDENT = " " * 21


def _farm_header():
    for line in FARM_ART:
        console.print(Text(FARM_INDENT) + _gradient_text(line, FARM_GRADIENT))
    console.print(_gradient_text(" " * 22 + "Universal Farm — Interactive TUI",
                                 [(0.0, (255, 20, 147)), (1.0, (148, 0, 211))]))


TUI_BANNER = r"""
[bold cyan]
                     ███████╗ █████╗ ██████╗ ███╗   ███╗
                     ██╔════╝██╔══██╗██╔══██╗████╗ ████║
                     █████╗  ███████║██████╔╝██╔████╔██║
                     ██╔══╝  ██╔══██║██╔══██╗██║╚██╔╝██║
                     ██║     ██║  ██║██║  ██║██║ ╚═╝ ██║
                     ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝
[/bold cyan]
[bold bright_cyan]                    TokenHarbor Farm — Interactive TUI[/bold bright_cyan]
"""


HARBOR_BANNER = r"""
[bold cyan]
               ██╗  ██╗ █████╗ ██████╗ ██████╗  ██████╗ ██████╗
               ██║  ██║██╔══██╗██╔══██╗██╔══██╗██╔═══██╗██╔══██╗
               ███████║███████║██████╔╝██████╔╝██║   ██║██████╔╝
               ██╔══██║██╔══██║██╔══██╗██╔══██╗██║   ██║██╔══██╗
               ██║  ██║██║  ██║██║  ██║██████╔╝╚██████╔╝██║  ██║
               ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚═╝  ╚═╝
[/bold cyan]
[bold bright_cyan]                 TokenHarbor Auto CLI — HTTP Mode • Chromium[/bold bright_cyan]
[dim italic]                              FORKED FROM MASANTOID[/dim italic]
"""


def _header():
    _farm_header()


MISTRAL_BANNER = r"""
[bold magenta]
               ███╗   ███╗██╗███████╗████████╗██████╗  █████╗ ██╗
               ████╗ ████║██║██╔════╝╚══██╔══╝██╔══██╗██╔══██╗██║
               ██╔████╔██║██║███████╗   ██║   ██████╔╝███████║██║
               ██║╚██╔╝██║██║╚════██║   ██║   ██╔══██╗██╔══██║██║
               ██║ ╚═╝ ██║██║███████║   ██║   ██║  ██║██║  ██║███████╗
               ╚═╝     ╚═╝╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
[/bold magenta]
[bold bright_magenta]              Mistral Farm Auto CLI — HTTP Mode • No Browser[/bold bright_magenta]
"""


def _mistral_header():
    console.print(MISTRAL_BANNER)


DAHL_BANNER = r"""
[bold green]
                         ██████╗  █████╗ ██╗  ██╗██╗
                         ██╔══██╗██╔══██╗██║  ██║██║
                         ██║  ██║███████║███████║██║
                         ██║  ██║██╔══██║██╔══██║██║
                         ██████╔╝██║  ██║██║  ██║███████╗
                         ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝
[/bold green]
[bold bright_green]                   Dahl Farm Auto CLI — HTTP Mode • No Browser[/bold bright_green]
"""


def _dahl_header():
    console.print(DAHL_BANNER)


def _harbor_header():
    console.print(HARBOR_BANNER)


def _status_line(state: dict, proxies: list, tempik, capsolver) -> None:
    def dot(ok: bool) -> str:
        return "[bright_green]●[/bright_green]" if ok else "[bright_red]●[/bright_red]"
    proxy_txt = f"{len(proxies)} proxies" if proxies else "no proxy"
    console.print(
        f"{dot(bool(proxies))} [white]{proxy_txt}[/white]   "
        f"{dot(bool(tempik))} [white]tempik[/white]   "
        f"{dot(bool(capsolver))} [white]capsolver[/white]   "
        f"[dim]│[/dim]   [dim]delay[/dim] [cyan]{state['delay']}s[/cyan]",
        justify="center",
    )


def _get_capsolver() -> str | None:
    if CAPSOLVER_PATH.exists():
        k = CAPSOLVER_PATH.read_text().strip()
        return k or None
    return None


def _set_capsolver(key: str) -> None:
    CAPSOLVER_PATH.write_text(key.strip() + "\n")
    os.chmod(CAPSOLVER_PATH, 0o600)


def menu_setup_capsolver():
    _clear_screen(); _harbor_header()
    current = _get_capsolver()
    masked = (current[:8] + "..." if current else "-")
    console.print(f"\nCurrent Capsolver key: [cyan]{masked}[/cyan]\n")
    val = Prompt.ask("Enter Capsolver API key (empty to clear, 'q' to cancel)",
                     password=True)
    if val.lower() == "q":
        return
    if not val.strip():
        if CAPSOLVER_PATH.exists():
            CAPSOLVER_PATH.unlink()
        console.print("[yellow]Capsolver key cleared.[/yellow]")
    else:
        _set_capsolver(val)
        console.print("[green]Capsolver key saved.[/green]")
    Prompt.ask("\nPress Enter to continue", default="")


def menu_setup_proxy():
    while True:
        _clear_screen(); _header()
        proxies = _get_proxies()
        console.print(f"\n[bold]Proxy management[/bold] — [cyan]{len(proxies)}[/cyan] configured\n")
        console.print("\\[1] Add proxy (bulk paste)")
        console.print("\\[2] Select to delete (multi-select)")
        console.print("[3] Delete all proxies")
        console.print("[0] Back\n")
        choice = Prompt.ask("Select", choices=["0", "1", "2", "3"],
                            default="1", show_choices=False)
        if choice == "1":
            _proxy_add_bulk()
        elif choice == "2":
            _proxy_select_delete()
        elif choice == "3":
            _proxy_delete_all()
        else:
            return


def _proxy_add_bulk():
    _clear_screen(); _header()
    console.print("\n[dim]Format per line: user:pass@host:port[/dim]")
    console.print("[dim]Paste proxies (one per line). Type DONE on its own line when finished.[/dim]\n")
    lines = []
    while True:
        try:
            line = input("proxy> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/yellow]")
            Prompt.ask("\nPress Enter to continue", default="")
            return
        if line.lower() == "q" and not lines:
            return
        if line.upper() == "DONE":
            break
        if line:
            for part in line.split(","):
                part = part.strip()
                if part and part.upper() != "DONE":
                    lines.append(part)
    if not lines:
        console.print("[dim]No proxies added.[/dim]")
    else:
        existing = _get_proxies()
        _set_proxies(existing + lines)
        console.print(f"[green]{len(lines)} proxy/proxies added ({len(existing) + len(lines)} total).[/green]")
    Prompt.ask("\nPress Enter to continue", default="")


def _proxy_delete_all():
    _clear_screen(); _header()
    proxies = _get_proxies()
    if not proxies:
        console.print("\n[dim]No proxies to delete.[/dim]")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    if Confirm.ask(f"\n[red]Delete all {len(proxies)} proxies?[/red]", default=False):
        PROXY_PATH.unlink()
        console.print("[green]✓ All proxies deleted.[/green]")
    else:
        console.print("Cancelled.")
    Prompt.ask("\nPress Enter to continue", default="")


def _proxy_select_delete():
    proxies = _get_proxies()
    if not proxies:
        _clear_screen(); _header()
        console.print("\n[dim]No proxies to delete.[/dim]")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    selected = _curses_multiselect(
        "Select proxies to delete (↑↓ navigate, SPACE toggle, ENTER delete, q cancel)",
        proxies,
    )
    if selected is None:
        return  # cancelled
    if not selected:
        _clear_screen(); _header()
        console.print("\n[dim]Nothing selected.[/dim]")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    _clear_screen(); _header()
    console.print(f"\n[red]Delete {len(selected)} selected proxy/proxies?[/red]")
    for p in selected:
        masked = p.split("@")[-1] if "@" in p else p
        console.print(f"  • {masked}")
    if Confirm.ask("", default=False):
        remaining = [p for p in proxies if p not in selected]
        if remaining:
            _set_proxies(remaining)
        elif PROXY_PATH.exists():
            PROXY_PATH.unlink()
        console.print(f"[green]✓ {len(selected)} deleted ({len(remaining)} remaining).[/green]")
    else:
        console.print("Cancelled.")
    Prompt.ask("\nPress Enter to continue", default="")


def _curses_multiselect(title: str, items: list) -> list | None:
    """Interactive multi-select. Returns selected items, [] if none, None if cancelled."""
    import curses

    selected_idx = set()
    cursor = 0
    result = {"cancelled": False}

    def draw(stdscr):
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        stdscr.addstr(0, 0, title[:w - 1], curses.A_BOLD)
        stdscr.addstr(1, 0, f"{len(selected_idx)} selected", curses.A_DIM)
        for i, item in enumerate(items):
            y = i + 3
            if y >= h - 1:
                break
            masked = item.split("@")[-1] if "@" in item else item
            mark = "[x]" if i in selected_idx else "[ ]"
            line = f"{mark} {masked}"
            attr = curses.A_REVERSE if i == cursor else curses.A_NORMAL
            try:
                stdscr.addstr(y, 2, line[:w - 4], attr)
            except curses.error:
                pass
        stdscr.refresh()

    def loop(stdscr):
        nonlocal cursor
        curses.curs_set(0)
        stdscr.keypad(True)
        while True:
            draw(stdscr)
            key = stdscr.getch()
            if key == curses.KEY_UP:
                cursor = (cursor - 1) % len(items)
            elif key == curses.KEY_DOWN:
                cursor = (cursor + 1) % len(items)
            elif key == ord(" "):
                if cursor in selected_idx:
                    selected_idx.discard(cursor)
                else:
                    selected_idx.add(cursor)
            elif key in (curses.KEY_ENTER, 10, 13):
                break
            elif key in (ord("q"), ord("Q"), 27):  # q / Esc
                result["cancelled"] = True
                break

    try:
        curses.wrapper(loop)
    except Exception:
        return None
    if result["cancelled"]:
        return None
    return [items[i] for i in sorted(selected_idx)]


def menu_setup_tempik():
    _clear_screen(); _harbor_header()
    current = _get_tempik_url()
    console.print(f"\nCurrent Tempik URL: [cyan]{current or '-'}[/cyan]\n")
    val = Prompt.ask("Enter Tempik base URL ('q' to cancel)")
    if val.lower() == "q":
        return
    if val.strip():
        _set_tempik_url(val.strip().rstrip("/"))
        console.print("[green]Tempik URL saved.[/green]")
    Prompt.ask("\nPress Enter to continue", default="")


def menu_delay_setting():
    _clear_screen(); _header()
    state = _load_state()
    console.print(f"\nCurrent delay: [cyan]{state['delay']}s[/cyan]")
    console.print("[dim]Seconds to wait between accounts (rate-limit safety).[/dim]\n")
    val = IntPrompt.ask("Enter delay in seconds", default=state["delay"])
    state["delay"] = max(0, val)
    _save_state(state)
    console.print(f"[green]Delay set to {state['delay']}s.[/green]")
    Prompt.ask("\nPress Enter to continue", default="")


def menu_run_farm():
    _clear_screen(); _harbor_header()
    # Pre-flight checks.
    tempik = _get_tempik_url()
    if not tempik:
        console.print("\n[red]✗ Tempik URL is not set.[/red]")
        console.print("Set it first via [cyan]Setup tempik[/cyan] menu.")
        Prompt.ask("\nPress Enter to continue", default="")
        return

    capsolver = _get_capsolver()
    if not capsolver:
        console.print("\n[red]✗ Capsolver key is not set.[/red]")
        console.print("Set it first via [cyan]Setup capsolver key[/cyan] menu.")
        Prompt.ask("\nPress Enter to continue", default="")
        return

    proxies = _get_proxies()
    if not proxies:
        console.print("\n[yellow]⚠ No proxy configured.[/yellow]")
        if not Confirm.ask("Run without proxy?", default=False):
            console.print("Cancelled. Set proxies via [cyan]Setup proxy[/cyan].")
            Prompt.ask("\nPress Enter to continue", default="")
            return
        proxy_info = "no"
    else:
        proxy_info = f"{len(proxies)} (rotating)"

    state = _load_state()
    count = IntPrompt.ask("\nHow many accounts to farm?", default=1)
    delay = state.get("delay", DEFAULT_DELAY)
    console.print(f"\n[dim]Tempik: {tempik}[/dim]")
    console.print(f"[dim]Proxy: {proxy_info}[/dim]")
    console.print(f"[dim]Delay: {delay}s[/dim]\n")

    if not Confirm.ask(f"Start farming {count} account(s)?", default=True):
        return

    # Foreground or background?
    console.print()
    console.print("\\[1] Run in foreground (watch live)")
    console.print("\\[2] Run in background (survives disconnect)")
    bg_choice = Prompt.ask("Mode", choices=["1", "2"], default="1",
                           show_choices=False)

    console.print()
    venv_python = REPO_DIR / ".venv" / "bin" / "python"
    py = str(venv_python) if venv_python.exists() else sys.executable
    cmd = [py, "-m", "tools.tokenharbor.cli", "browser-farm",
           "--count", str(count), "--delay", str(delay)]

    if bg_choice == "2":
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        logfile = f"/tmp/farm-{ts}.log"
        pidfile = Path("/tmp/farm.pid")
        # nohup + detach so it survives SSH disconnect.
        with open(logfile, "w") as lf:
            proc = subprocess.Popen(
                ["nohup"] + cmd,
                cwd=str(REPO_DIR),
                stdout=lf, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        pidfile.write_text(str(proc.pid))
        console.print(f"[green]✓ Farm started in background (PID {proc.pid}).[/green]")
        console.print(f"[dim]Log: {logfile}[/dim]")
        console.print("[dim]You can disconnect — it keeps running.[/dim]")
        console.print("[dim]Check progress via menu [2] Results → [b] Background log.[/dim]")
        # Arm monitor if auto-inject ON or Telegram configured.
        state = _load_state()
        if _should_arm_monitor(state, "tokenharbor_auto_inject"):
            _arm_inject_monitor("/root/tokenharbor_inject_monitor.py", proc.pid, ts, "tokenharbor")
    else:
        try:
            subprocess.run(cmd, cwd=str(REPO_DIR))
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
        # Auto-inject to 9Router if enabled.
        state = _load_state()
        if state.get("tokenharbor_auto_inject", False):
            console.print("\n[dim]Auto-injecting to 9Router...[/dim]")
            added, skipped, err = _inject_tokenharbor_to_9router()
            if err:
                console.print(f"[red]Inject failed: {err}[/red]")
            else:
                console.print(f"[green]✓ Injected: {added} new, {skipped} already there.[/green]")
        # Telegram notification.
        try:
            accounts = _get_accounts()
            ok_keys = [a["api_key"] for a in accounts if a.get("ok") and a.get("api_key")]
            total = len(accounts)
            success = len(ok_keys)
            _notify_farm_done("TokenHarbor", total, success, total - success, ok_keys)
        except Exception:
            pass
    Prompt.ask("\nPress Enter to continue", default="")


def _count_running_farms() -> int:
    """Count background farm processes currently alive."""
    count = 0
    # Check PID file.
    pidfile = Path("/tmp/farm.pid")
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            count += 1
        except (ValueError, OSError):
            pass
    # Also scan for browser-farm processes not in pidfile.
    try:
        out = subprocess.run(["pgrep", "-f", "browser-farm"],
                             capture_output=True, text=True, timeout=5)
        pids = [p for p in out.stdout.strip().split("\n") if p.strip()]
        # Subtract the one we already counted via pidfile.
        if pidfile.exists():
            try:
                known = pidfile.read_text().strip()
                pids = [p for p in pids if p != known]
            except OSError:
                pass
        count += len(pids)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return count


def _count_failed_from_logs() -> int:
    """Count 'Failed at' occurrences across farm log files."""
    total = 0
    for log in Path("/tmp").glob("farm-*.log"):
        try:
            text = log.read_text()
            total += text.count("✗ Failed at")
        except OSError:
            pass
    return total


def _get_accounts() -> list:
    """Read all TokenHarbor farm accounts from account.json."""
    if not RESULTS_PATH.exists():
        return []
    try:
        data = json.loads(RESULTS_PATH.read_text())
        accounts = data if isinstance(data, list) else [data]
        return accounts if isinstance(accounts, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def menu_results():
    _clear_screen(); _harbor_header()
    # Gather stats even if account.json doesn't exist yet.
    accounts = []
    if RESULTS_PATH.exists():
        try:
            data = json.loads(RESULTS_PATH.read_text())
            accounts = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            console.print("\n[red]Results file is corrupted.[/red]")
    ok = [a for a in accounts if a.get("ok")]
    fail_file = [a for a in accounts if not a.get("ok")]

    running = _count_running_farms()
    failed_logs = _count_failed_from_logs()
    failed_total = len(fail_file) + failed_logs

    console.print(f"\n[bold]Running: [cyan]{running}[/cyan] | "
                  f"[green]Success: {len(ok)}[/green] | "
                  f"[red]Failed: {failed_total}[/red][/bold]\n")
    if not accounts and not failed_logs and running == 0:
        console.print("[dim]No results yet. Run farm first.[/dim]")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    if ok:
        t = Table(title="Farmed accounts", show_lines=True)
        t.add_column("#", style="dim", width=3)
        t.add_column("Email", style="magenta")
        t.add_column("API key", style="green")
        t.add_column("Free models", width=11)
        for i, a in enumerate(ok, 1):
            t.add_row(str(i), a.get("email", "-"),
                      a.get("api_key", "-"),
                      "yes" if a.get("free_models") else "no")
        console.print(t)
    if fail_file:
        console.print("\n[red]Failed:[/red]")
        for a in fail_file:
            console.print(f"  • {a.get('email', '?')}: "
                          f"{a.get('stage', '?')} — {a.get('error', '?')}")

    # Sub-menu: use Text to avoid Rich parsing [c]/[d]/[b] as color tags.
    from rich.text import Text as _Text
    console.print()
    bar = _Text()
    if ok:
        bar.append("[c] ", style="bold cyan")
        bar.append("Copy all API  ")
        bar.append("[d] ", style="bold cyan")
        bar.append("Delete all results  ")
    pidfile = Path("/tmp/farm.pid")
    bg_running = False
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            bg_running = True
        except (ValueError, OSError):
            pass
    has_logs = bool(list(Path("/tmp").glob("farm-*.log")))
    if bg_running or has_logs:
        bar.append("[b] ", style="bold cyan")
        bar.append("Background log  ")
    bar.append("[Enter] ", style="bold cyan")
    bar.append("Back to menu")
    console.print(bar)
    choices = ["c", "d", "b", ""] if ok else (["b", ""] if (bg_running or has_logs) else [""])
    action = Prompt.ask("Action", choices=choices,
                        default="", show_choices=False)
    if action == "c" and ok:
        _copy_keys(ok)
    elif action == "d" and ok:
        _delete_results()
    elif action == "b":
        _show_bg_log()
    else:
        Prompt.ask("\nPress Enter to continue", default="")


def _copy_keys(accounts: list) -> None:
    keys = [a.get("api_key", "") for a in accounts if a.get("api_key")]
    text = "\n".join(keys)
    copied = False
    # Try system clipboard.
    for cmd in (["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"]):
        try:
            subprocess.run(cmd, input=text.encode(), timeout=5,
                           capture_output=True)
            copied = True
            break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    # Always also save to a file for easy retrieval over SSH.
    keys_file = REPO_DIR / "keys.txt"
    keys_file.write_text(text + "\n")
    console.print(f"\n[green]✓ {len(keys)} keys ready.[/green]")
    if copied:
        console.print("[dim]Copied to clipboard.[/dim]")
    console.print(f"[dim]Also saved to: {keys_file}[/dim]")
    console.print("\n[bold]Keys:[/bold]")
    for k in keys:
        console.print(f"  {k}")
    Prompt.ask("\nPress Enter to continue", default="")


def _show_bg_log() -> None:
    logs = sorted(Path("/tmp").glob("farm-*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        console.print("\n[dim]No background farm logs found.[/dim]")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    latest = logs[-1]
    # Check if still running.
    pidfile = Path("/tmp/farm.pid")
    running = False
    if pidfile.exists():
        try:
            os.kill(int(pidfile.read_text().strip()), 0)
            running = True
        except (ValueError, OSError):
            pass
    status = "[green]RUNNING[/green]" if running else "[dim]finished[/dim]"
    console.print(f"\n[bold]Background farm:[/bold] {status}")
    console.print(f"[dim]Log: {latest}[/dim]\n")
    try:
        lines = latest.read_text().splitlines()
    except OSError:
        lines = []
    # Show last 30 lines.
    for line in lines[-30:]:
        console.print(f"  {line}")
    if running:
        console.print("\n[dim]Still running — check again later for updates.[/dim]")
    Prompt.ask("\nPress Enter to continue", default="")


def _delete_results() -> None:
    if not Confirm.ask("\n[red]Delete ALL farm results (emails + keys + logs)?[/red]",
                       default=False):
        console.print("Cancelled.")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    if RESULTS_PATH.exists():
        RESULTS_PATH.unlink()
    keys_file = REPO_DIR / "keys.txt"
    if keys_file.exists():
        keys_file.unlink()
    # Clear farm logs so the Failed counter resets too.
    for log in Path("/tmp").glob("farm-*.log"):
        try:
            log.unlink()
        except OSError:
            pass
    # Clear stale PID file.
    pidfile = Path("/tmp/farm.pid")
    if pidfile.exists():
        try:
            pidfile.unlink()
        except OSError:
            pass
    console.print("[green]✓ All results deleted (counter reset).[/green]")
    Prompt.ask("\nPress Enter to continue", default="")


def menu_tokenharbor():
    """TokenHarbor submenu (was the old main menu)."""
    while True:
        _clear_screen()
        _harbor_header()
        console.print()
        state = _load_state()
        proxies = _get_proxies()
        tempik = _get_tempik_url()
        capsolver = _get_capsolver()

        _status_line(state, proxies, tempik, capsolver)
        th_inject_on = state.get("tokenharbor_auto_inject", False)
        console.print(f"  [dim]auto-inject:[/dim] {'[green]ON[/green]' if th_inject_on else '[dim]OFF[/dim]'}",
                      justify="center")
        console.print()

        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("key", style="bold bright_cyan", width=5, justify="right")
        menu.add_column("label", style="white")
        menu.add_column("hint", style="dim")
        menu.add_row("[1]", "Run farm", "start farming accounts")
        menu.add_row("[2]", "Results", "view farmed accounts")
        menu.add_row("[3]", "Setup tempik", "disposable email URL")
        menu.add_row("[4]", "Setup capsolver key", "captcha solver API key")
        menu.add_row("[5]", "Auto inject 9Router", f"currently {('ON' if th_inject_on else 'OFF')}")
        menu.add_row("[0]", "Back", "")
        console.print(menu, justify="center")
        console.print()
        choice = Prompt.ask("    [dim]Select Action[/dim]", choices=["0", "1", "2", "3", "4", "5"],
                            default="1", show_choices=False, show_default=False)
        if choice == "1":
            menu_run_farm()
        elif choice == "2":
            menu_results()
        elif choice == "3":
            menu_setup_tempik()
        elif choice == "4":
            menu_setup_capsolver()
        elif choice == "5":
            menu_tokenharbor_inject_toggle()
        else:
            return


# ═══════════════════════════════════════════════════════════════════════════════
# Mistral farm submenu
# ═══════════════════════════════════════════════════════════════════════════════

def _get_mistral_keys() -> list:
    """Parse /root/mistral_keys.txt -> list of dicts."""
    if not MISTRAL_KEYS.exists():
        return []
    out = []
    for line in MISTRAL_KEYS.read_text().splitlines():
        parts = line.strip().split("|")
        if len(parts) < 5:
            continue
        out.append({
            "email": parts[0],
            "password": parts[1],
            "session_token": parts[2],
            "status": parts[3],
            "api_key": parts[4],
            "ok": parts[3] == "KEYED",
        })
    return out


def _inject_tokenharbor_to_9router() -> tuple:
    """Inject TokenHarbor keys into 9Router SQLite. Returns (added, skipped, error)."""
    import sqlite3, uuid
    from datetime import datetime, timezone
    DB = '/var/lib/9router/db/data.sqlite'
    PREFIX = 'HrbrFarm'
    BASE_URL = 'https://tokenharbor.ai/v1'
    NODE_NAME = 'hrbrfarm'

    def now():
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

    def get_accounts():
        if not RESULTS_PATH.exists():
            return []
        try:
            data = json.loads(RESULTS_PATH.read_text())
            accounts = data if isinstance(data, list) else [data]
            return [a for a in accounts if a.get("ok") and a.get("api_key")]
        except (json.JSONDecodeError, OSError):
            return []

    try:
        conn = sqlite3.connect(DB)
    except Exception as e:
        return 0, 0, f"DB open failed: {e}"

    try:
        # Find existing node by baseUrl (reuse user's node regardless of prefix).
        node_id = None
        prefix = PREFIX
        try:
            row = conn.execute(
                "SELECT id, data FROM providerNodes WHERE json_extract(data, '$.baseUrl') = ?",
                (BASE_URL,)).fetchone()
        except Exception:
            row = None
        if row:
            node_id = row[0]
            try:
                prefix = (json.loads(row[1]) or {}).get('prefix') or PREFIX
            except Exception:
                pass
        if not node_id:
            node_id = f'openai-compatible-chat-{uuid.uuid4()}'
            data = json.dumps({'prefix': PREFIX, 'apiType': 'chat', 'baseUrl': BASE_URL, 'nodeName': NODE_NAME})
            conn.execute('INSERT INTO providerNodes (id,type,name,data,createdAt,updatedAt) VALUES (?,?,?,?,?,?)',
                         (node_id, 'openai-compatible', NODE_NAME, data, now(), now()))
            conn.commit()

        have = set()
        try:
            for (raw,) in conn.execute('SELECT data FROM providerConnections WHERE provider=?', (node_id,)):
                try:
                    k = (json.loads(raw) or {}).get('apiKey')
                    if k:
                        have.add(k)
                except Exception:
                    pass
        except Exception:
            pass

        added = skipped = 0
        for a in get_accounts():
            key, email = a.get("api_key"), a.get("email", "")
            if not key:
                continue
            if key in have:
                skipped += 1
                continue
            n = conn.execute('SELECT COUNT(*) FROM providerConnections WHERE provider=?', (node_id,)).fetchone()[0] + 1
            data = json.dumps({
                'apiKey': key, 'authType': 'apikey', 'testStatus': 'active', 'backoffLevel': 0,
                'providerSpecificData': {'prefix': prefix, 'apiType': 'chat', 'baseUrl': BASE_URL,
                                          'nodeName': NODE_NAME, 'label': email},
            })
            conn.execute('INSERT INTO providerConnections (id,provider,authType,name,email,priority,isActive,data,createdAt,updatedAt) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (str(uuid.uuid4()), node_id, 'apikey', f'Key {n}', None, 1, 1, data, now(), now()))
            conn.commit()
            have.add(key)
            added += 1
        conn.close()
        return added, skipped, None
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return 0, 0, str(e)


def _inject_mistral_to_9router() -> tuple:
    """Inject Mistral keys into 9Router SQLite. Returns (added, skipped, error)."""
    import sqlite3, uuid
    from datetime import datetime, timezone
    DB = '/var/lib/9router/db/data.sqlite'
    PREFIX = 'mstrlfarm'
    BASE_URL = 'https://api.mistral.ai/v1'
    NODE_NAME = 'mstrlfarm'
    DEFAULT_MODEL = 'mistral-large-4'

    def now():
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

    try:
        conn = sqlite3.connect(DB)
    except Exception as e:
        return 0, 0, f"DB open failed: {e}"

    try:
        # Find existing node by baseUrl (reuse user's node regardless of prefix).
        node_id = None
        prefix = PREFIX
        try:
            row = conn.execute(
                "SELECT id, data FROM providerNodes WHERE json_extract(data, '$.baseUrl') = ?",
                (BASE_URL,)).fetchone()
        except Exception:
            row = None
        if row:
            node_id = row[0]
            try:
                prefix = (json.loads(row[1]) or {}).get('prefix') or PREFIX
            except Exception:
                pass
        if not node_id:
            node_id = f'openai-compatible-chat-{uuid.uuid4()}'
            data = json.dumps({'prefix': PREFIX, 'apiType': 'chat', 'baseUrl': BASE_URL, 'nodeName': NODE_NAME})
            conn.execute('INSERT INTO providerNodes (id,type,name,data,createdAt,updatedAt) VALUES (?,?,?,?,?,?)',
                         (node_id, 'openai-compatible', NODE_NAME, data, now(), now()))
            conn.commit()

        # Existing keys
        have = set()
        try:
            for (raw,) in conn.execute('SELECT data FROM providerConnections WHERE provider=?', (node_id,)):
                try:
                    k = (json.loads(raw) or {}).get('apiKey')
                    if k:
                        have.add(k)
                except Exception:
                    pass
        except Exception:
            pass

        added = skipped = 0
        for k in _get_mistral_keys():
            key, email = k["api_key"], k["email"]
            if not key or not k["ok"]:
                continue
            if key in have:
                skipped += 1
                continue
            n = conn.execute('SELECT COUNT(*) FROM providerConnections WHERE provider=?', (node_id,)).fetchone()[0] + 1
            data = json.dumps({
                'apiKey': key, 'authType': 'apikey', 'testStatus': 'active', 'backoffLevel': 0,
                'defaultModel': DEFAULT_MODEL,
                'providerSpecificData': {'prefix': prefix, 'apiType': 'chat', 'baseUrl': BASE_URL,
                                          'nodeName': NODE_NAME, 'label': email},
            })
            conn.execute('INSERT INTO providerConnections (id,provider,authType,name,email,priority,isActive,data,createdAt,updatedAt) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (str(uuid.uuid4()), node_id, 'apikey', f'Key {n}', None, 1, 1, data, now(), now()))
            conn.commit()
            have.add(key)
            added += 1
        conn.close()
        return added, skipped, None
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return 0, 0, str(e)


def _count_mistral_running() -> int:
    """Count running mistral_farm.py processes."""
    try:
        out = subprocess.run(["pgrep", "-f", "mistral_farm.py"],
                             capture_output=True, text=True, timeout=5)
        pids = [p for p in out.stdout.strip().split("\n") if p.strip()]
        return len(pids)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0


def menu_mistral_run_farm():
    _clear_screen(); _mistral_header()
    console.print()
    if not MISTRAL_SCRIPT.exists():
        console.print(f"[red]✗ Mistral farm script not found: {MISTRAL_SCRIPT}[/red]")
        Prompt.ask("\nPress Enter to continue", default="")
        return

    proxies = _get_proxies()
    if not proxies:
        console.print("[yellow]⚠ No proxy configured.[/yellow]")
        console.print("Set proxies via main menu [magenta]Setup Proxy[/magenta].")
        Prompt.ask("\nPress Enter to continue", default="")
        return

    count = IntPrompt.ask("\nHow many keys to farm?", default=1)
    console.print(f"\n[dim]Proxy: {len(proxies)} (rotating)[/dim]")
    console.print(f"[dim]Script: {MISTRAL_SCRIPT}[/dim]\n")

    if not Confirm.ask(f"Start farming {count} Mistral key(s)?", default=True):
        return

    console.print()
    console.print("[1] Run in foreground (watch live)")
    console.print("[2] Run in background (survives disconnect)")
    bg_choice = Prompt.ask("Mode", choices=["1", "2"], default="1",
                           show_choices=False)

    cmd = [sys.executable, str(MISTRAL_SCRIPT), "--count", str(count)]
    if bg_choice == "2":
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        logfile = f"/tmp/mistral-farm-{ts}.log"
        with open(logfile, "w") as lf:
            proc = subprocess.Popen(
                ["nohup"] + cmd,
                stdout=lf, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        console.print(f"[green]✓ Mistral farm started in background (PID {proc.pid}).[/green]")
        console.print(f"[dim]Log: {logfile}[/dim]")
        # Arm monitor if auto-inject ON or Telegram configured.
        state = _load_state()
        if _should_arm_monitor(state, "mistral_auto_inject"):
            _arm_inject_monitor("/root/mistral_inject_monitor.py", proc.pid, ts, "mistral")
    else:
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
        # Auto-inject to 9Router if enabled.
        state = _load_state()
        if state.get("mistral_auto_inject", False):
            console.print("\n[dim]Auto-injecting to 9Router...[/dim]")
            added, skipped, err = _inject_mistral_to_9router()
            if err:
                console.print(f"[red]Inject failed: {err}[/red]")
            else:
                console.print(f"[green]✓ Injected: {added} new, {skipped} already there.[/green]")
        # Telegram notification.
        try:
            keys = _get_mistral_keys()
            ok_keys = [k["api_key"] for k in keys if k.get("ok") and k.get("api_key")]
            total = len(keys)
            success = len(ok_keys)
            _notify_farm_done("Mistral", total, success, total - success, ok_keys)
        except Exception:
            pass
    Prompt.ask("\nPress Enter to continue", default="")


def menu_mistral_results():
    _clear_screen(); _mistral_header()
    console.print()
    keys = _get_mistral_keys()
    ok = [k for k in keys if k["ok"]]
    running = _count_mistral_running()

    console.print(f"[bold]Running: [magenta]{running}[/magenta] | "
                  f"[green]Success: {len(ok)}[/green] | "
                  f"[dim]Total: {len(keys)}[/dim][/bold]\n")
    if ok:
        t = Table(title="Mistral API keys", show_lines=True)
        t.add_column("#", style="dim", width=3)
        t.add_column("Email", style="magenta")
        t.add_column("API key", style="green")
        for i, k in enumerate(ok, 1):
            t.add_row(str(i), k["email"], k["api_key"])
        console.print(t)
    elif not keys and running == 0:
        console.print("[dim]No results yet. Run farm first.[/dim]")

    # Actions
    from rich.text import Text as _Text
    console.print()
    bar = _Text()
    if ok:
        bar.append("[c] ", style="bold magenta")
        bar.append("Copy all API  ")
        bar.append("[d] ", style="bold magenta")
        bar.append("Delete all results  ")
    bar.append("[Enter] ", style="bold magenta")
    bar.append("Back")
    console.print(bar)
    choices = ["c", "d", ""] if ok else [""]
    action = Prompt.ask("Action", choices=choices, default="", show_choices=False)
    if action == "c" and ok:
        text = "\n".join(k["api_key"] for k in ok)
        kf = Path("/root/mistral_keys_export.txt")
        kf.write_text(text + "\n")
        console.print(f"[green]✓ {len(ok)} keys saved to {kf}[/green]")
        for k in ok:
            console.print(f"  {k['api_key']}")
        Prompt.ask("\nPress Enter to continue", default="")
    elif action == "d" and ok:
        if Confirm.ask("\n[red]Delete ALL Mistral results?[/red]", default=False):
            MISTRAL_KEYS.unlink(missing_ok=True)
            kf = Path("/root/mistral_keys_export.txt")
            kf.unlink(missing_ok=True)
            for log in Path("/tmp").glob("mistral-farm-*.log"):
                try:
                    log.unlink()
                except OSError:
                    pass
            console.print("[green]✓ All Mistral results deleted.[/green]")
        Prompt.ask("\nPress Enter to continue", default="")


def menu_mistral():
    """Mistral farm submenu."""
    while True:
        _clear_screen()
        _mistral_header()
        console.print()
        proxies = _get_proxies()
        running = _count_mistral_running()
        keys = _get_mistral_keys()
        ok = len([k for k in keys if k["ok"]])
        state = _load_state()
        inject_on = state.get("mistral_auto_inject", False)
        inject_txt = "[green]ON[/green]" if inject_on else "[dim]OFF[/dim]"

        console.print(f"[dim]proxy:[/dim] {'[green]' + str(len(proxies)) + ' set[/green]' if proxies else '[red]not set[/red]'}   "
                      f"[dim]running:[/dim] [magenta]{running}[/magenta]   "
                      f"[dim]keys:[/dim] [green]{ok}[/green]   "
                      f"[dim]auto-inject:[/dim] {inject_txt}\n",
                      justify="center")

        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("key", style="bold bright_magenta", width=5, justify="right")
        menu.add_column("label", style="white")
        menu.add_column("hint", style="dim")
        menu.add_row("[1]", "Run farm", "farm Mistral API keys")
        menu.add_row("[2]", "Results", f"{ok} keys farmed")
        menu.add_row("[3]", "Auto inject 9Router", f"currently {('ON' if inject_on else 'OFF')}")
        menu.add_row("[0]", "Back", "")
        console.print(menu, justify="center")
        console.print()
        choice = Prompt.ask("    [dim]Select Action[/dim]", choices=["0", "1", "2", "3"],
                            default="1", show_choices=False, show_default=False)
        if choice == "1":
            menu_mistral_run_farm()
        elif choice == "2":
            menu_mistral_results()
        elif choice == "3":
            menu_mistral_inject_toggle()
        else:
            return


def _check_9router() -> tuple:
    """Check if 9Router is installed. Returns (ok: bool, msg: str)."""
    db = Path('/var/lib/9router/db/data.sqlite')
    if not db.exists():
        return False, "9Router is not installed on this server."
    # Verify the expected tables exist.
    try:
        import sqlite3
        conn = sqlite3.connect(str(db))
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        if 'providerNodes' not in tables or 'providerConnections' not in tables:
            return False, "9Router DB found but schema is incomplete."
        return True, "9Router detected."
    except Exception as e:
        return False, f"9Router DB check failed: {e}"


def menu_tokenharbor_inject_toggle():
    _clear_screen(); _harbor_header()
    console.print()
    state = _load_state()
    current = state.get("tokenharbor_auto_inject", False)
    console.print(f"\nAuto inject 9Router is currently: "
                  f"{'[green]ON[/green]' if current else '[dim]OFF[/dim]'}")
    console.print("[dim]ON = new keys are auto-injected to 9Router (prefix HrbrFarm).[/dim]")
    console.print("[dim]OFF = injection disabled.[/dim]\n")
    console.print("[1] Turn ON")
    console.print("[2] Turn OFF")
    console.print("[0] Back\n")
    choice = Prompt.ask("Select", choices=["0", "1", "2"], default="0",
                        show_choices=False)
    if choice == "1":
        ok, msg = _check_9router()
        if not ok:
            console.print(f"\n[red]✗ {msg}[/red]")
            Prompt.ask("\nPress Enter to continue", default="")
            return
        console.print(f"\n[dim]✓ {msg}[/dim]")
        state["tokenharbor_auto_inject"] = True
        _save_state(state)
        console.print("[green]✓ Auto inject 9Router: ON[/green]")
        added, skipped, err = _inject_tokenharbor_to_9router()
        if err:
            console.print(f"[red]Inject failed: {err}[/red]")
        else:
            console.print(f"[dim]Injected now: {added} added, {skipped} already there.[/dim]")
    elif choice == "2":
        state["tokenharbor_auto_inject"] = False
        _save_state(state)
        console.print("\n[dim]Auto inject 9Router: OFF[/dim]")
    Prompt.ask("\nPress Enter to continue", default="")


def menu_mistral_inject_toggle():
    _clear_screen(); _mistral_header()
    console.print()
    state = _load_state()
    current = state.get("mistral_auto_inject", False)
    console.print(f"\nAuto inject 9Router is currently: "
                  f"{'[green]ON[/green]' if current else '[dim]OFF[/dim]'}")
    console.print("[dim]ON = new keys are auto-injected to 9Router after farming.[/dim]")
    console.print("[dim]OFF = injection disabled.[/dim]\n")
    console.print("[1] Turn ON")
    console.print("[2] Turn OFF")
    console.print("[0] Back\n")
    choice = Prompt.ask("Select", choices=["0", "1", "2"], default="0",
                        show_choices=False)
    if choice == "1":
        # Verify 9Router is installed before enabling.
        ok, msg = _check_9router()
        if not ok:
            console.print(f"\n[red]✗ {msg}[/red]")
            Prompt.ask("\nPress Enter to continue", default="")
            return
        console.print(f"\n[dim]✓ {msg}[/dim]")
        state["mistral_auto_inject"] = True
        _save_state(state)
        console.print("[green]✓ Auto inject 9Router: ON[/green]")
        # Inject any existing keys now
        added, skipped, err = _inject_mistral_to_9router()
        if err:
            console.print(f"[red]Inject failed: {err}[/red]")
        else:
            console.print(f"[dim]Injected now: {added} added, {skipped} already there.[/dim]")
    elif choice == "2":
        state["mistral_auto_inject"] = False
        _save_state(state)
        console.print("\n[dim]Auto inject 9Router: OFF[/dim]")
    Prompt.ask("\nPress Enter to continue", default="")


# ═══════════════════════════════════════════════════════════════════════════════
# Dahl farm
# ═══════════════════════════════════════════════════════════════════════════════

def _get_dahl_keys() -> list:
    """Parse /root/dahl_keys.txt -> list of dicts."""
    if not DAHL_KEYS.exists():
        return []
    out = []
    for line in DAHL_KEYS.read_text().splitlines():
        parts = line.strip().split("|")
        if len(parts) < 4:
            continue
        out.append({
            "username": parts[0],
            "fingerprint": parts[1],
            "status": parts[2],
            "api_key": parts[3],
            "ok": parts[2] == "ok",
        })
    return out


def _count_dahl_running() -> int:
    count = 0
    try:
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                cmd = (proc / "cmdline").read_text()
                if "dahl_farm.py" in cmd and "inject_monitor" not in cmd:
                    count += 1
            except OSError:
                pass
    except OSError:
        pass
    return count


def _inject_dahl_to_9router() -> tuple:
    """Inject Dahl keys into 9Router SQLite. Returns (added, skipped, error)."""
    import sqlite3, uuid
    from datetime import datetime, timezone
    DB = '/var/lib/9router/db/data.sqlite'
    PREFIX = 'DahlFarm'
    BASE_URL = 'https://inference.dahl.global/v1'
    NODE_NAME = 'dahltfarm'

    def now():
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')

    try:
        conn = sqlite3.connect(DB)
    except Exception as e:
        return 0, 0, f"DB open failed: {e}"

    try:
        # Find existing node by baseUrl (reuse user's node regardless of prefix).
        node_id = None
        prefix = PREFIX
        try:
            row = conn.execute(
                "SELECT id, data FROM providerNodes WHERE json_extract(data, '$.baseUrl') = ?",
                (BASE_URL,)).fetchone()
        except Exception:
            row = None
        if row:
            node_id = row[0]
            try:
                prefix = (json.loads(row[1]) or {}).get('prefix') or PREFIX
            except Exception:
                pass
        if not node_id:
            node_id = f'openai-compatible-chat-{uuid.uuid4()}'
            data = json.dumps({'prefix': PREFIX, 'apiType': 'chat', 'baseUrl': BASE_URL, 'nodeName': NODE_NAME})
            conn.execute('INSERT INTO providerNodes (id,type,name,data,createdAt,updatedAt) VALUES (?,?,?,?,?,?)',
                         (node_id, 'openai-compatible', NODE_NAME, data, now(), now()))
            conn.commit()

        have = set()
        try:
            for (raw,) in conn.execute('SELECT data FROM providerConnections WHERE provider=?', (node_id,)):
                try:
                    k = (json.loads(raw) or {}).get('apiKey')
                    if k:
                        have.add(k)
                except Exception:
                    pass
        except Exception:
            pass

        added = skipped = 0
        for k in _get_dahl_keys():
            key, username = k["api_key"], k["username"]
            if not key or not k["ok"]:
                continue
            if key in have:
                skipped += 1
                continue
            n = conn.execute('SELECT COUNT(*) FROM providerConnections WHERE provider=?', (node_id,)).fetchone()[0] + 1
            data = json.dumps({
                'apiKey': key, 'authType': 'apikey', 'testStatus': 'active', 'backoffLevel': 0,
                'providerSpecificData': {'prefix': prefix, 'apiType': 'chat', 'baseUrl': BASE_URL,
                                          'nodeName': NODE_NAME, 'label': username},
            })
            conn.execute('INSERT INTO providerConnections (id,provider,authType,name,email,priority,isActive,data,createdAt,updatedAt) VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (str(uuid.uuid4()), node_id, 'apikey', f'Key {n}', None, 1, 1, data, now(), now()))
            conn.commit()
            have.add(key)
            added += 1
        conn.close()
        return added, skipped, None
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return 0, 0, str(e)


def menu_dahl_run_farm():
    _clear_screen(); _dahl_header()
    console.print()
    if not DAHL_SCRIPT.exists():
        console.print(f"[red]✗ Dahl farm script not found: {DAHL_SCRIPT}[/red]")
        Prompt.ask("\nPress Enter to continue", default="")
        return

    count = IntPrompt.ask("\nHow many keys to farm?", default=1)
    console.print(f"\n[dim]Script: {DAHL_SCRIPT}[/dim]")
    console.print("[dim]Pure HTTP — no browser, no email, no captcha.[/dim]\n")

    if not Confirm.ask(f"Start farming {count} Dahl key(s)?", default=True):
        return

    console.print()
    console.print("[1] Run in foreground (watch live)")
    console.print("[2] Run in background (survives disconnect)")
    bg_choice = Prompt.ask("Mode", choices=["1", "2"], default="1",
                           show_choices=False)

    cmd = [sys.executable, str(DAHL_SCRIPT), "--count", str(count)]
    if bg_choice == "2":
        import datetime as _dt
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        logfile = f"/tmp/dahl-farm-{ts}.log"
        with open(logfile, "w") as lf:
            proc = subprocess.Popen(
                ["nohup"] + cmd,
                stdout=lf, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        console.print(f"[green]✓ Dahl farm started in background (PID {proc.pid}).[/green]")
        console.print(f"[dim]Log: {logfile}[/dim]")
        # Arm monitor if auto-inject ON or Telegram configured.
        state = _load_state()
        if _should_arm_monitor(state, "dahl_auto_inject"):
            _arm_inject_monitor("/root/dahl_inject_monitor.py", proc.pid, ts, "dahl")
    else:
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted.[/yellow]")
        # Auto-inject to 9Router if enabled.
        state = _load_state()
        if state.get("dahl_auto_inject", False):
            console.print("\n[dim]Auto-injecting to 9Router...[/dim]")
            added, skipped, err = _inject_dahl_to_9router()
            if err:
                console.print(f"[red]Inject failed: {err}[/red]")
            else:
                console.print(f"[green]✓ Injected: {added} new, {skipped} already there.[/green]")
        # Telegram notification.
        try:
            keys = _get_dahl_keys()
            ok_keys = [k["api_key"] for k in keys if k.get("ok") and k.get("api_key")]
            total = len(keys)
            success = len(ok_keys)
            _notify_farm_done("Dahl", total, success, total - success, ok_keys)
        except Exception:
            pass
    Prompt.ask("\nPress Enter to continue", default="")


def menu_dahl_results():
    _clear_screen(); _dahl_header()
    console.print()
    keys = _get_dahl_keys()
    ok = [k for k in keys if k["ok"]]
    running = _count_dahl_running()

    console.print(f"[bold]Running: [green]{running}[/green] | "
                  f"[green]Success: {len(ok)}[/green] | "
                  f"[dim]Total: {len(keys)}[/dim][/bold]\n",
                  justify="center")
    if ok:
        t = Table(title="Dahl API keys", show_lines=True)
        t.add_column("#", style="dim", width=3)
        t.add_column("Username", style="green")
        t.add_column("API key", style="green")
        for i, k in enumerate(ok, 1):
            t.add_row(str(i), k["username"], k["api_key"])
        console.print(t)
    elif not keys and running == 0:
        console.print("[dim]No results yet. Run farm first.[/dim]")

    from rich.text import Text as _Text
    console.print()
    bar = _Text()
    if ok:
        bar.append("[c] ", style="bold green")
        bar.append("Copy all API  ")
        bar.append("[d] ", style="bold green")
        bar.append("Delete all results  ")
    bar.append("[Enter] ", style="bold green")
    bar.append("Back")
    console.print(bar)
    choices = ["c", "d", ""] if ok else [""]
    action = Prompt.ask("Action", choices=choices, default="", show_choices=False)
    if action == "c" and ok:
        text = "\n".join(k["api_key"] for k in ok)
        kf = Path("/root/dahl_keys_export.txt")
        kf.write_text(text + "\n")
        console.print(f"[green]✓ {len(ok)} keys saved to {kf}[/green]")
        for k in ok:
            console.print(f"  {k['api_key']}")
        Prompt.ask("\nPress Enter to continue", default="")
    elif action == "d" and ok:
        if Confirm.ask("\n[red]Delete ALL Dahl results?[/red]", default=False):
            DAHL_KEYS.unlink(missing_ok=True)
            kf = Path("/root/dahl_keys_export.txt")
            kf.unlink(missing_ok=True)
            for log in Path("/tmp").glob("dahl-farm-*.log"):
                try:
                    log.unlink()
                except OSError:
                    pass
            console.print("[green]✓ All Dahl results deleted.[/green]")
        Prompt.ask("\nPress Enter to continue", default="")


def menu_dahl_inject_toggle():
    _clear_screen(); _dahl_header()
    console.print()
    state = _load_state()
    current = state.get("dahl_auto_inject", False)
    console.print(f"\nAuto inject 9Router is currently: "
                  f"{'[green]ON[/green]' if current else '[dim]OFF[/dim]'}")
    console.print("[dim]ON = new keys are auto-injected to 9Router (prefix DahlFarm).[/dim]")
    console.print("[dim]OFF = injection disabled.[/dim]\n")
    console.print("[1] Turn ON")
    console.print("[2] Turn OFF")
    console.print("[0] Back\n")
    choice = Prompt.ask("Select", choices=["0", "1", "2"], default="0",
                        show_choices=False)
    if choice == "1":
        ok, msg = _check_9router()
        if not ok:
            console.print(f"\n[red]✗ {msg}[/red]")
            Prompt.ask("\nPress Enter to continue", default="")
            return
        console.print(f"\n[dim]✓ {msg}[/dim]")
        state["dahl_auto_inject"] = True
        _save_state(state)
        console.print("[green]✓ Auto inject 9Router: ON[/green]")
        added, skipped, err = _inject_dahl_to_9router()
        if err:
            console.print(f"[red]Inject failed: {err}[/red]")
        else:
            console.print(f"[dim]Injected now: {added} added, {skipped} already there.[/dim]")
    elif choice == "2":
        state["dahl_auto_inject"] = False
        _save_state(state)
        console.print("\n[dim]Auto inject 9Router: OFF[/dim]")
    Prompt.ask("\nPress Enter to continue", default="")


def menu_dahl():
    """Dahl farm submenu."""
    while True:
        _clear_screen()
        _dahl_header()
        console.print()
        running = _count_dahl_running()
        keys = _get_dahl_keys()
        ok = len([k for k in keys if k["ok"]])
        state = _load_state()
        inject_on = state.get("dahl_auto_inject", False)
        inject_txt = "[green]ON[/green]" if inject_on else "[dim]OFF[/dim]"

        console.print(f"[dim]running:[/dim] [green]{running}[/green]   "
                      f"[dim]keys:[/dim] [green]{ok}[/green]   "
                      f"[dim]auto-inject:[/dim] {inject_txt}\n",
                      justify="center")

        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("key", style="bold bright_green", width=5, justify="right")
        menu.add_column("label", style="white")
        menu.add_column("hint", style="dim")
        menu.add_row("[1]", "Run farm", "farm Dahl API keys")
        menu.add_row("[2]", "Results", f"{ok} keys farmed")
        menu.add_row("[3]", "Auto inject 9Router", f"currently {('ON' if inject_on else 'OFF')}")
        menu.add_row("[0]", "Back", "")
        console.print(menu, justify="center")
        console.print()
        choice = Prompt.ask("    [dim]Select Action[/dim]", choices=["0", "1", "2", "3"],
                            default="1", show_choices=False, show_default=False)
        if choice == "1":
            menu_dahl_run_farm()
        elif choice == "2":
            menu_dahl_results()
        elif choice == "3":
            menu_dahl_inject_toggle()
        else:
            return


# ═══════════════════════════════════════════════════════════════════════════════
# Parallel farm
# ═══════════════════════════════════════════════════════════════════════════════


def _should_arm_monitor(state: dict, inject_key: str) -> bool:
    """Arm monitor if auto-inject is ON or Telegram is configured."""
    if state.get(inject_key, False):
        return True
    return bool(state.get("telegram_bot_token") and state.get("telegram_chat_id"))


def _arm_inject_monitor(monitor_path: str, pid: int, ts: str, label: str):
    """Spawn inject+notify monitor for a background farm PID."""
    monitor = Path(monitor_path)
    if not monitor.exists():
        console.print(f"[yellow]⚠ Monitor script not found: {monitor_path}[/yellow]")
        return
    mlog = f"/tmp/{label}-inject-{ts}.log"
    with open(mlog, "w") as mlf:
        subprocess.Popen(
            ["nohup", sys.executable, str(monitor), str(pid)],
            stdout=mlf, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    console.print(f"[dim]  {label} monitor armed[/dim]")


def _get_running_farms() -> list:
    """Return list of (name, pid, logfile) for running farm processes."""
    running = []
    # TokenHarbor: check pidfile + scan.
    pidfile = Path("/tmp/farm.pid")
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            logs = sorted(Path("/tmp").glob("farm-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
            running.append(("TokenHarbor", pid, str(logs[0]) if logs else "-"))
        except (ValueError, OSError):
            pass
    # Mistral + Dahl: scan /proc.
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cmd = (proc / "cmdline").read_text().replace("\x00", " ")
            if "dahl_farm.py" in cmd and "inject_monitor" not in cmd:
                logs = sorted(Path("/tmp").glob("dahl-farm-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
                running.append(("Dahl", int(proc.name), str(logs[0]) if logs else "-"))
            elif "mistral_farm.py" in cmd and "inject_monitor" not in cmd:
                logs = sorted(Path("/tmp").glob("mistral-farm-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
                running.append(("Mistral", int(proc.name), str(logs[0]) if logs else "-"))
        except OSError:
            pass
    return running


def menu_parallel_status():
    _clear_screen(); _header()
    console.print("\n[bold]  Parallel Farm — Status[/bold]\n")
    running = _get_running_farms()
    if not running:
        console.print("[dim]No farms running.[/dim]\n")
    else:
        t = Table(show_header=True, box=None, padding=(0, 2))
        t.add_column("Farm", style="white")
        t.add_column("PID", style="dim")
        t.add_column("Log", style="dim")
        for name, pid, log in running:
            t.add_row(name, str(pid), log)
        console.print(t)
        console.print()
        console.print("[dim]Pilih nomor untuk lihat log, [0] kembali[/dim]\n")
        for i, (name, pid, log) in enumerate(running, 1):
            console.print(f"[{i}] Lihat log {name}")
        console.print("[0] Back\n")
        c = Prompt.ask("Select", choices=[str(i) for i in range(len(running) + 1)],
                       default="0", show_choices=False)
        if c != "0":
            name, pid, log = running[int(c) - 1]
            if log != "-" and Path(log).exists():
                console.print(f"\n[dim]--- {log} (20 baris terakhir) ---[/dim]")
                lines = Path(log).read_text().splitlines()[-20:]
                for line in lines:
                    console.print(f"[dim]{line}[/dim]")
            else:
                console.print("[yellow]Log tidak ditemukan.[/yellow]")
            Prompt.ask("\nPress Enter to continue", default="")
            return
    Prompt.ask("Press Enter to continue", default="")


def menu_parallel_farm():
    _clear_screen(); _header()
    console.print("\n[bold]  Parallel Farm[/bold]\n")

    # Submenu: start new or check status.
    console.print("[1] Start new parallel farm")
    console.print("[2] Check running farms")
    console.print("[0] Back\n")
    c = Prompt.ask("Select", choices=["0", "1", "2"], default="1",
                   show_choices=False)
    if c == "2":
        menu_parallel_status()
        return
    if c == "0":
        return

    console.print("[dim]Run multiple farms simultaneously in background.[/dim]\n")

    proxies = _get_proxies()
    if not proxies:
        console.print("[yellow]⚠ No proxy configured.[/yellow]")
        console.print("Set proxies via main menu [magenta]Setup Proxy[/magenta].")
        Prompt.ask("\nPress Enter to continue", default="")
        return

    # Step 1: select which farms to run (arrow keys + space).
    chosen = _curses_multiselect(
        "Select APIs to farm (↑↓ navigate, SPACE toggle, ENTER done, q cancel)",
        ["TokenHarbor", "Mistral", "Dahl"],
    )
    if chosen is None:
        return  # cancelled with q
    if not chosen:
        console.print("\n[yellow]No farm selected.[/yellow]")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    selected = [(str(i + 1), name) for i, name in enumerate(
        ["TokenHarbor", "Mistral", "Dahl"]) if name in chosen]

    # Validate prerequisites per selected farm.
    tempik = _get_tempik_url()
    capsolver = _get_capsolver()
    state = _load_state()
    delay = state.get("delay", DEFAULT_DELAY)
    problems = []
    if any(name == "TokenHarbor" for _, name in selected):
        if not tempik or not capsolver:
            problems.append("TokenHarbor needs Tempik URL + Capsolver key.")
        venv_python = REPO_DIR / ".venv" / "bin" / "python"
    if any(name == "Mistral" for _, name in selected):
        if not MISTRAL_SCRIPT.exists():
            problems.append(f"Mistral script not found: {MISTRAL_SCRIPT}")
    if any(name == "Dahl" for _, name in selected):
        if not DAHL_SCRIPT.exists():
            problems.append(f"Dahl script not found: {DAHL_SCRIPT}")
    if problems:
        for p in problems:
            console.print(f"[red]✗ {p}[/red]")
        Prompt.ask("\nPress Enter to continue", default="")
        return

    # Step 2: same batch count for all, or per farm?
    console.print()
    console.print("[1] Same batch count for all farms")
    console.print("[2] Different count per farm")
    mode = Prompt.ask("Batch mode", choices=["1", "2"], default="1",
                      show_choices=False)
    counts = {}
    if mode == "1":
        same = IntPrompt.ask("\nBatch count for all farms?", default=5)
        for _, name in selected:
            counts[name] = same
    else:
        for _, name in selected:
            counts[name] = IntPrompt.ask(f"{name} count?", default=5)

    console.print()
    for _, name in selected:
        console.print(f"[dim]{name}: {counts[name]}[/dim]")
    console.print()
    if not Confirm.ask(f"Start {len(selected)} farm(s) in background?", default=True):
        return

    import datetime as _dt
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    procs = {}

    # TokenHarbor farm
    if "TokenHarbor" in counts:
        py = str(venv_python) if venv_python.exists() else sys.executable
        th_cmd = [py, "-m", "tools.tokenharbor.cli", "browser-farm",
                  "--count", str(counts["TokenHarbor"]), "--delay", str(delay)]
        th_log = f"/tmp/farm-{ts}.log"
        with open(th_log, "w") as lf:
            th_proc = subprocess.Popen(["nohup"] + th_cmd, cwd=str(REPO_DIR),
                                       stdout=lf, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        procs["TokenHarbor"] = (th_proc, th_log)

    # Mistral farm
    if "Mistral" in counts:
        mistral_cmd = [sys.executable, str(MISTRAL_SCRIPT),
                       "--count", str(counts["Mistral"])]
        mistral_log = f"/tmp/mistral-farm-{ts}.log"
        with open(mistral_log, "w") as lf:
            mistral_proc = subprocess.Popen(["nohup"] + mistral_cmd,
                                            stdout=lf, stderr=subprocess.STDOUT,
                                            start_new_session=True)
        procs["Mistral"] = (mistral_proc, mistral_log)

    # Dahl farm
    if "Dahl" in counts:
        dahl_cmd = [sys.executable, str(DAHL_SCRIPT),
                    "--count", str(counts["Dahl"])]
        dahl_log = f"/tmp/dahl-farm-{ts}.log"
        with open(dahl_log, "w") as lf:
            dahl_proc = subprocess.Popen(["nohup"] + dahl_cmd,
                                         stdout=lf, stderr=subprocess.STDOUT,
                                         start_new_session=True)
        procs["Dahl"] = (dahl_proc, dahl_log)

    console.print()
    for name, (proc, log) in procs.items():
        console.print(f"[green]✓ {name} farm started (PID {proc.pid})[/green]")
        console.print(f"[dim]  Log: {log}[/dim]")

    # Arm monitors if auto-inject ON or Telegram configured.
    state = _load_state()
    _monitors = {
        "TokenHarbor": ("tokenharbor_auto_inject", "/root/tokenharbor_inject_monitor.py", "tokenharbor"),
        "Mistral": ("mistral_auto_inject", "/root/mistral_inject_monitor.py", "mistral"),
        "Dahl": ("dahl_auto_inject", "/root/dahl_inject_monitor.py", "dahl"),
    }
    for name, (proc, _) in procs.items():
        inject_key, mon_path, label = _monitors[name]
        if _should_arm_monitor(state, inject_key):
            _arm_inject_monitor(mon_path, proc.pid, ts, label)

    console.print("\n[dim]All keep running after disconnect.[/dim]")
    Prompt.ask("\nPress Enter to continue", default="")


def _send_telegram(text: str) -> tuple:
    """Send Telegram notification. Returns (ok: bool, msg: str)."""
    import urllib.request
    state = _load_state()
    token = state.get("telegram_bot_token")
    chat_id = state.get("telegram_chat_id")
    if not token or not chat_id:
        return False, "Telegram not configured."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                return True, "Sent."
            return False, result.get("description", "Unknown error")
    except Exception as e:
        return False, str(e)


_INJECT_STATE_KEYS = {
    "TokenHarbor": "tokenharbor_auto_inject",
    "Mistral": "mistral_auto_inject",
    "Dahl": "dahl_auto_inject",
}


def _notify_farm_done(provider: str, total: int, success: int, failed: int,
                      keys: list = None):
    """Send farm completion notification to Telegram if configured."""
    import html as _html
    state = _load_state()
    if not state.get("telegram_bot_token") or not state.get("telegram_chat_id"):
        return
    inject_on = state.get(_INJECT_STATE_KEYS.get(provider, ""), False)
    inject_txt = "ON 🟢" if inject_on else "OFF 🔴"

    title = f"✅ Farm Selesai — {provider}"
    text = (
        f"{title.center(40)}\n"
        f"📦 Total batch: {total}.     🟢 Success: {success}.    🔴 Failed: {failed}\n"
        f"\n\n\n"
        f"🔑 {len(keys or [])} API Key:\n"
    )
    if keys:
        # Code block -> Telegram shows COPY CODE button.
        escaped = "\n".join(_html.escape(k) for k in keys)
        text += f"<pre>{escaped}</pre>\n"
    text += f"\n🔄 Auto inject 9Router: <b>{inject_txt}</b>"
    ok, msg = _send_telegram(text)
    return ok


def menu_setup_telegram():
    _clear_screen(); _header()
    console.print("\n[bold bright_cyan]  Setup Bot Telegram[/bold bright_cyan]\n")
    state = _load_state()
    cur_token = state.get("telegram_bot_token", "")
    cur_chat = state.get("telegram_chat_id", "")
    if cur_token:
        console.print(f"  [dim]Bot token:[/dim] [green]set ({cur_token[:10]}...)")
        console.print(f"  [dim]Chat ID:[/dim] [green]{cur_chat}[/green]\n")
    else:
        console.print("  [dim]Belum dikonfigurasi.[/dim]\n")

    console.print("[1] Set / update Bot Token & Chat ID")
    console.print("[2] Test kirim pesan")
    console.print("[3] Hapus konfigurasi")
    console.print("[0] Back\n")
    choice = Prompt.ask("Select", choices=["0", "1", "2", "3"], default="0",
                        show_choices=False)
    if choice == "1":
        token = Prompt.ask("Bot Token", default=cur_token or "")
        chat_id = Prompt.ask("Chat ID", default=cur_chat or "")
        if token and chat_id:
            state["telegram_bot_token"] = token.strip()
            state["telegram_chat_id"] = chat_id.strip()
            _save_state(state)
            console.print("\n[green]✓ Telegram dikonfigurasi.[/green]")
        else:
            console.print("\n[yellow]Dibatalkan — token dan chat ID wajib diisi.[/yellow]")
    elif choice == "2":
        if not cur_token or not cur_chat:
            console.print("\n[yellow]Belum dikonfigurasi. Set dulu via [1].[/yellow]")
        else:
            ok, msg = _send_telegram("🔔 <b>Test notifikasi</b>\nBot Telegram terhubung!")
            if ok:
                console.print("\n[green]✓ Pesan test terkirim![/green]")
            else:
                console.print(f"\n[red]✗ Gagal: {msg}[/red]")
    elif choice == "3":
        state.pop("telegram_bot_token", None)
        state.pop("telegram_chat_id", None)
        _save_state(state)
        console.print("\n[dim]Konfigurasi Telegram dihapus.[/dim]")
    Prompt.ask("\nPress Enter to continue", default="")


def main():
    while True:
        _clear_screen()
        _header()
        state = _load_state()
        proxies = _get_proxies()
        tempik = _get_tempik_url()
        capsolver = _get_capsolver()

        _status_line(state, proxies, tempik, capsolver)
        console.print()

        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("key", width=5, justify="right")
        menu.add_column("label", style="white")
        menu.add_column("hint", style="dim")
        # Gradient numbers: sample FARM_GRADIENT across the menu items.
        _nums = ["1", "2", "3", "4", "5", "6", "7", "0"]
        def _gnum(n):
            idx = _nums.index(n)
            t = idx / max(len(_nums) - 1, 1)
            for s in range(len(FARM_GRADIENT) - 1):
                p0, c0 = FARM_GRADIENT[s]
                p1, c1 = FARM_GRADIENT[s + 1]
                if p0 <= t <= p1:
                    f = (t - p0) / max(p1 - p0, 1e-9)
                    r = int(c0[0] + (c1[0] - c0[0]) * f)
                    g = int(c0[1] + (c1[1] - c0[1]) * f)
                    b = int(c0[2] + (c1[2] - c0[2]) * f)
                    break
            else:
                r, g, b = FARM_GRADIENT[-1][1]
            return Text(f"[{n}]", style=f"bold #{r:02x}{g:02x}{b:02x}")
        menu.add_row(_gnum("1"), "Farm TokenHarbor", "TokenHarbor account farming")
        menu.add_row(_gnum("2"), "Farm Mistral keys", "Mistral API key farming")
        menu.add_row(_gnum("3"), "Farm Dahl keys", "Dahl Inference API keys")
        menu.add_row(_gnum("4"), "Parallel farm", "run both farms in background")
        menu.add_row(_gnum("5"), "Delay setting", f"currently {state['delay']}s")
        menu.add_row(_gnum("6"), "Setup Proxy", f"{len(proxies)} configured" if proxies else "not configured")
        menu.add_row(_gnum("7"), "Setup Bot Tele", "Telegram notifications")
        menu.add_row(_gnum("0"), "Exit", "")
        console.print(menu, justify="center")
        console.print()
        choice = Prompt.ask("    [dim]Select Action[/dim]", choices=["0", "1", "2", "3", "4", "5", "6", "7"],
                            default="1", show_choices=False, show_default=False)
        if choice == "1":
            menu_tokenharbor()
        elif choice == "2":
            menu_mistral()
        elif choice == "3":
            menu_dahl()
        elif choice == "4":
            menu_parallel_farm()
        elif choice == "5":
            menu_delay_setting()
        elif choice == "6":
            menu_setup_proxy()
        elif choice == "7":
            menu_setup_telegram()
        else:
            console.print("\nBye.")
            break


if __name__ == "__main__":
    main()

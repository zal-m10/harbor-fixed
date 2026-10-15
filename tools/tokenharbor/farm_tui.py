"""Interactive TUI for TokenHarbor farming.

Launched via the `farm` command after running install.sh.
Menu: Run farm | Results | Setup proxy | Setup tempik | Delay setting
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from rich.console import Console
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

DEFAULT_DELAY = 60


def _load_state() -> dict:
    if TUI_STATE.exists():
        try:
            return json.loads(TUI_STATE.read_text())
        except json.JSONDecodeError:
            pass
    return {"delay": DEFAULT_DELAY}


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


def _header():
    console.print(TUI_BANNER)


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
    _clear_screen(); _header()
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
    _clear_screen(); _header()
    current = _get_proxies()
    console.print(f"\nCurrent proxies: [cyan]{len(current)}[/cyan]")
    for p in current:
        masked = p.split("@")[-1] if "@" in p else p
        console.print(f"  • {masked}")
    console.print("\n[dim]Format per line: user:pass@host:port[/dim]")
    console.print("[dim]Paste proxies (one per line). Type DONE on its own line when finished.[/dim]")
    console.print("[dim]Or type 'q' to cancel, empty line then DONE to clear.[/dim]\n")
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
            # Also handle comma-separated on one line.
            for part in line.split(","):
                part = part.strip()
                if part and part.upper() != "DONE":
                    lines.append(part)
    if not lines:
        if PROXY_PATH.exists():
            PROXY_PATH.unlink()
        console.print("[yellow]Proxies cleared.[/yellow]")
    else:
        _set_proxies(lines)
        console.print(f"[green]{len(lines)} proxy/proxies saved.[/green]")
    Prompt.ask("\nPress Enter to continue", default="")


def menu_setup_tempik():
    _clear_screen(); _header()
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
    _clear_screen(); _header()
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

    console.print()
    venv_python = REPO_DIR / ".venv" / "bin" / "python"
    py = str(venv_python) if venv_python.exists() else sys.executable
    cmd = [py, "-m", "tools.tokenharbor.cli", "browser-farm",
           "--count", str(count), "--delay", str(delay)]
    try:
        subprocess.run(cmd, cwd=str(REPO_DIR))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    Prompt.ask("\nPress Enter to continue", default="")


def menu_results():
    _clear_screen(); _header()
    if not RESULTS_PATH.exists():
        console.print("\n[dim]No results yet. Run farm first.[/dim]")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    try:
        data = json.loads(RESULTS_PATH.read_text())
    except json.JSONDecodeError:
        console.print("\n[red]Results file is corrupted.[/red]")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    accounts = data if isinstance(data, list) else [data]
    ok = [a for a in accounts if a.get("ok")]
    fail = [a for a in accounts if not a.get("ok")]

    console.print(f"\n[bold]Total: {len(accounts)} | "
                  f"[green]Success: {len(ok)}[/green] | "
                  f"[red]Failed: {len(fail)}[/red][/bold]\n")
    if ok:
        t = Table(title="Farmed accounts", show_lines=True)
        t.add_column("#", style="dim", width=3)
        t.add_column("Email", style="cyan")
        t.add_column("API key", style="green")
        t.add_column("Free models", width=11)
        for i, a in enumerate(ok, 1):
            t.add_row(str(i), a.get("email", "-"),
                      a.get("api_key", "-"),
                      "yes" if a.get("free_models") else "no")
        console.print(t)
    if fail:
        console.print("\n[red]Failed:[/red]")
        for a in fail:
            console.print(f"  • {a.get('email', '?')}: "
                          f"{a.get('stage', '?')} — {a.get('error', '?')}")

    # Sub-menu: copy keys / delete results (horizontal).
    if ok:
        console.print()
        console.print("[cyan][c][/cyan] Copy all API keys  "
                      "[cyan][d][/cyan] Delete all results  "
                      "[cyan][Enter][/cyan] Back to menu")
        action = Prompt.ask("Action", choices=["c", "d", ""],
                            default="", show_choices=False)
        if action == "c":
            _copy_keys(ok)
        elif action == "d":
            _delete_results()
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


def _delete_results() -> None:
    if not Confirm.ask("\n[red]Delete ALL farm results (emails + keys)?[/red]",
                       default=False):
        console.print("Cancelled.")
        Prompt.ask("\nPress Enter to continue", default="")
        return
    if RESULTS_PATH.exists():
        RESULTS_PATH.unlink()
    keys_file = REPO_DIR / "keys.txt"
    if keys_file.exists():
        keys_file.unlink()
    console.print("[green]✓ All results deleted.[/green]")
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
        menu.add_column("key", style="bold bright_cyan", width=5, justify="right")
        menu.add_column("label", style="white")
        menu.add_column("hint", style="dim")
        menu.add_row("[1]", "Run farm", "start farming accounts")
        menu.add_row("[2]", "Results", "view farmed accounts")
        menu.add_row("[3]", "Setup proxy", f"{len(proxies)} configured" if proxies else "not configured")
        menu.add_row("[4]", "Setup tempik", "disposable email URL")
        menu.add_row("[5]", "Setup capsolver key", "captcha solver API key")
        menu.add_row("[6]", "Delay setting", f"currently {state['delay']}s")
        menu.add_row("[0]", "Exit", "")
        console.print(menu, justify="center")
        console.print()
        choice = Prompt.ask("[dim]Select[/dim]", choices=["0", "1", "2", "3", "4", "5", "6"],
                            default="1", show_choices=False)
        if choice == "1":
            menu_run_farm()
        elif choice == "2":
            menu_results()
        elif choice == "3":
            menu_setup_proxy()
        elif choice == "4":
            menu_setup_tempik()
        elif choice == "5":
            menu_setup_capsolver()
        elif choice == "6":
            menu_delay_setting()
        else:
            console.print("\nBye.")
            break


if __name__ == "__main__":
    main()

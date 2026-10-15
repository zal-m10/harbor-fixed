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
PROXY_PATH = Path(__file__).resolve().parent / "proxies.txt"
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
    cfg.setdefault("files", {})["account_output"] = "account.json"
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


def _get_proxy() -> str | None:
    if PROXY_PATH.exists():
        p = PROXY_PATH.read_text().strip().splitlines()
        p = [x.strip() for x in p if x.strip() and not x.strip().startswith("#")]
        return p[0] if p else None
    return None


def _set_proxy(proxy: str) -> None:
    PROXY_PATH.write_text(proxy.strip() + "\n")


def _clear_screen():
    console.clear()


def _header():
    console.print(Panel(
        "[bold cyan]TokenHarbor Farm[/bold cyan] — interactive menu",
        style="cyan", expand=False))


def menu_setup_proxy():
    _clear_screen(); _header()
    current = _get_proxy()
    masked = (current.split("@")[-1] if current and "@" in current
              else (current or "-"))
    console.print(f"\nCurrent proxy: [cyan]{masked}[/cyan]")
    console.print("[dim]Format: user:pass@host:port[/dim]\n")
    val = Prompt.ask("Enter proxy (empty to clear, 'q' to cancel)")
    if val.lower() == "q":
        return
    if not val.strip():
        if PROXY_PATH.exists():
            PROXY_PATH.unlink()
        console.print("[yellow]Proxy cleared.[/yellow]")
    else:
        _set_proxy(val)
        console.print("[green]Proxy saved.[/green]")
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

    proxy = _get_proxy()
    if not proxy:
        console.print("\n[yellow]⚠ No proxy configured.[/yellow]")
        if not Confirm.ask("Run without proxy?", default=False):
            console.print("Cancelled. Set a proxy via [cyan]Setup proxy[/cyan].")
            Prompt.ask("\nPress Enter to continue", default="")
            return

    state = _load_state()
    count = IntPrompt.ask("\nHow many accounts to farm?", default=1)
    delay = state.get("delay", DEFAULT_DELAY)
    console.print(f"\n[dim]Tempik: {tempik}[/dim]")
    console.print(f"[dim]Proxy: {'yes' if proxy else 'no'}[/dim]")
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
    Prompt.ask("\nPress Enter to continue", default="")


def main():
    while True:
        _clear_screen(); _header()
        state = _load_state()
        proxy = _get_proxy()
        tempik = _get_tempik_url()
        console.print(f"\n[dim]proxy:[/dim] {'[green]set[/green]' if proxy else '[red]not set[/red]'}"
                      f"  [dim]tempik:[/dim] {'[green]set[/green]' if tempik else '[red]not set[/red]'}"
                      f"  [dim]delay:[/dim] [cyan]{state['delay']}s[/cyan]\n")
        console.print("[1] Run farm")
        console.print("[2] Results")
        console.print("[3] Setup proxy")
        console.print("[4] Setup tempik")
        console.print("[5] Delay setting")
        console.print("[0] Exit\n")
        choice = Prompt.ask("Select", choices=["0", "1", "2", "3", "4", "5"],
                            default="1")
        if choice == "1":
            menu_run_farm()
        elif choice == "2":
            menu_results()
        elif choice == "3":
            menu_setup_proxy()
        elif choice == "4":
            menu_setup_tempik()
        elif choice == "5":
            menu_delay_setting()
        else:
            console.print("\nBye.")
            break


if __name__ == "__main__":
    main()

"""
Capsolver Turnstile integration for TokenHarbor.
"""

import time
import requests
from pathlib import Path
from typing import Optional

# TokenHarbor signup page Turnstile sitekey
TURNSTILE_SITEKEY = "0x4AAAAAADBuC8Knz1EJZx9-"
TURNSTILE_URL = "https://tokenharbor.ai/login?mode=signup"


def _load_capsolver_key() -> str:
    """Load Capsolver API key from file."""
    key_file = Path(__file__).resolve().parent.parent / ".capsolver_key"
    if not key_file.exists():
        raise FileNotFoundError(
            f"Capsolver key file not found: {key_file}\n"
            "Create it with your Capsolver API key."
        )
    return key_file.read_text().strip()


def solve_turnstile(
    timeout: float = 90,
    poll_interval: float = 3,
) -> Optional[str]:
    """
    Solve a Turnstile captcha via Capsolver API.

    Returns the token string, or None on timeout/failure.
    """
    client_key = _load_capsolver_key()

    # Create task
    r = requests.post(
        "https://api.capsolver.com/createTask",
        json={
            "clientKey": client_key,
            "task": {
                "type": "AntiTurnstileTaskProxyLess",
                "websiteURL": TURNSTILE_URL,
                "websiteKey": TURNSTILE_SITEKEY,
            },
        },
        timeout=15,
    )
    data = r.json()
    if data.get("errorId") != 0:
        print(f"  Capsolver createTask error: {data.get('errorDescription', data)}")
        return None

    task_id = data["taskId"]

    # Poll for result
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll_interval)
        r = requests.post(
            "https://api.capsolver.com/getTaskResult",
            json={
                "clientKey": client_key,
                "taskId": task_id,
            },
            timeout=10,
        )
        data = r.json()
        if data.get("status") == "ready":
            return data["solution"]["token"]
        if data.get("errorId") != 0:
            print(f"  Capsolver getTaskResult error: {data.get('errorDescription', data)}")
            return None

    print("  Capsolver: timeout waiting for Turnstile solution")
    return None
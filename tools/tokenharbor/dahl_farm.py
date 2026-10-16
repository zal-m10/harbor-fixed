#!/usr/bin/env python3
"""
dahl_farm.py — Farm Dahl Inference (inference.dahl.global) API keys.

Pure HTTP, no browser, no email, no captcha.
  POST /v1/auth/signup {"username": ...} -> api_key + fingerprint
  GET  /v1/account                     -> welcome grant balance
  POST /v1/account/allocate            -> allocate balance to key
  POST /tokens + /v1/account/keys/claim (bonus)
  GET  /v1/models (Bearer)             -> verify key

Usage:
  python3 dahl_farm.py --count 5 [--proxy http://user:pass@host:port]

Output: /root/dahl_keys.txt  (username|fingerprint|status|api_key)
Progress: /root/dahl_farm_progress.txt
"""
import argparse, json, random, re, sys, time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    sys.exit(1)

WEB_BASE = "https://inference.dahl.global"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

KEYS_FILE = Path("/root/dahl_keys.txt")
PROGRESS_FILE = Path("/root/dahl_farm_progress.txt")

FIRST = ["agus", "budi", "sari", "dewi", "rudi", "maya", "eko", "fitri",
         "hendra", "nina", "yoga", "ratna", "dedi", "lia", "fajar", "wulan",
         "tomo", "siswa", "utomo", "pratama", "kusuma", "wijaya", "saputra",
         "nugroho", "rahmat", "indah", "bagus", "ayu", "dian", "rizky"]
LAST = ["pratama", "kusuma", "wijaya", "saputra", "nugroho", "santoso",
        "wibowo", "setiawan", "kurnia", "maulana", "firmansyah", "ramadhan"]


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(PROGRESS_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def gen_username():
    # 3-20 chars, alphanumeric/underscore, human-like.
    base = random.choice(FIRST) + random.choice(LAST)
    num = random.randint(100, 9999)
    u = f"{base}{num}"
    return u[:20]


def load_proxies():
    """Load proxies from the harbor proxy file (one per line)."""
    for p in [Path("/root/harbor-fixed/tools/proxies.txt"),
              Path("tools/proxies.txt")]:
        if p.exists():
            out = []
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    if not re.match(r"^\w+://", line):
                        line = "http://" + line
                    out.append(line)
            if out:
                return out
    return []


def farm_one(session, idx):
    username = gen_username()
    log(f"=== account #{idx} : {username} ===")

    # 1. Signup
    try:
        r = session.post(f"{WEB_BASE}/v1/auth/signup",
                         json={"username": username}, timeout=20)
    except Exception as e:
        log(f"  signup error: {e}")
        return None
    if r.status_code == 429:
        log("  rate limited (429)")
        return None
    if r.status_code != 201:
        log(f"  signup failed ({r.status_code}): {r.text[:120]}")
        return None
    try:
        data = r.json()
    except Exception:
        log("  signup: invalid JSON")
        return None

    fingerprint = data.get("fingerprint", "")
    key_obj = data.get("api_key") or {}
    key_id = key_obj.get("id")
    api_key = key_obj.get("token")
    if not api_key:
        log("  signup: no api_key in response")
        return None
    log(f"  signed up, key_id={key_id}")

    # 2. Check welcome grant
    balance = 0
    try:
        r2 = session.get(f"{WEB_BASE}/v1/account", timeout=20)
        if r2.status_code == 200:
            balance = r2.json().get("token_balance", 0)
            log(f"  welcome grant: {balance:,} tokens")
    except Exception as e:
        log(f"  account check: {e}")

    # 3. Allocate balance to key
    if balance > 0 and key_id:
        try:
            r3 = session.post(f"{WEB_BASE}/v1/account/allocate",
                              json={"key_id": key_id, "amount": balance},
                              timeout=20)
            if r3.status_code == 200:
                log(f"  allocated {balance:,} tokens to key")
        except Exception as e:
            log(f"  allocate: {e}")

    # Bonus: claim landing-page tokens
    try:
        r4 = session.post(f"{WEB_BASE}/tokens", timeout=10)
        if r4.status_code == 201:
            landing = r4.json().get("token")
            if landing:
                r5 = session.post(f"{WEB_BASE}/v1/account/keys/claim",
                                  json={"token": landing}, timeout=10)
                if r5.status_code == 200:
                    log("  bonus: claimed extra landing-page tokens")
    except Exception:
        pass

    # 4. Verify via /v1/models
    try:
        r6 = session.get(f"{WEB_BASE}/v1/models",
                         headers={"Authorization": f"Bearer {api_key}"},
                         timeout=20)
        if r6.status_code != 200:
            log(f"  verify failed ({r6.status_code})")
            return None
    except Exception as e:
        log(f"  verify error: {e}")
        return None

    log(f"  KEY: {api_key[:14]}... OK")
    return {"username": username, "fingerprint": fingerprint,
            "api_key": api_key, "ok": True}


def save_key(rec):
    line = f"{rec['username']}|{rec['fingerprint']}|ok|{rec['api_key']}\n"
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KEYS_FILE, "a") as f:
        f.write(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--proxy", default=None,
                    help="http://user:pass@host:port (overrides file)")
    ap.add_argument("--delay", type=int, default=5,
                    help="seconds between accounts")
    args = ap.parse_args()

    proxies = [args.proxy] if args.proxy else load_proxies()
    if proxies:
        log(f"proxies loaded: {len(proxies)}")
    else:
        log("WARNING: no proxy — running direct")

    ok = fail = 0
    for i in range(1, args.count + 1):
        proxy = random.choice(proxies) if proxies else None
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": WEB_BASE,
            "Referer": f"{WEB_BASE}/account",
        })
        if proxy:
            s.proxies = {"http": proxy, "https": proxy}
        try:
            rec = farm_one(s, i)
        except Exception as e:
            log(f"  unexpected: {e}")
            rec = None
        if rec:
            save_key(rec)
            ok += 1
        else:
            fail += 1
        if i < args.count:
            time.sleep(args.delay)

    log(f"=== DONE: {ok}/{args.count} success, {fail} failed ===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

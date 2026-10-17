#!/usr/bin/env python3
"""Monitor for Mistral background farm: inject to 9Router + Telegram notify.
Deployed by install.sh. Do not edit manually - edit the repo version instead.
"""
import sys
import time
import os
import json
from pathlib import Path

# Repo root = 3 levels up from this file: monitors/ -> tokenharbor/ -> tools/ -> repo
REPO_DIR = Path(__file__).resolve().parent.parent.parent.parent


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().split()[2] != "Z"
    except OSError:
        return False


def main():
    farm_pid = int(sys.argv[1])
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    before_keys = set(json.loads(sys.argv[3])) if len(sys.argv) > 3 else set()
    print(f"[monitor] Watching Mistral farm PID {farm_pid}...", flush=True)
    sys.path.insert(0, str(REPO_DIR))
    from tools.tokenharbor.farm_tui import (
        _inject_mistral_to_9router, _load_state, _get_mistral_keys,
        _notify_farm_done, NOTIFY_CHUNK)
    sent = set()
    while pid_alive(farm_pid):
        try:
            keys = _get_mistral_keys()
            fresh = [k["api_key"] for k in keys
                     if k.get("ok") and k.get("api_key")
                     and k["api_key"] not in before_keys and k["api_key"] not in sent]
            while len(fresh) >= NOTIFY_CHUNK:
                chunk = fresh[:NOTIFY_CHUNK]
                prog = f"{len(sent)+len(chunk)}/{count}" if count else f"{len(sent)+len(chunk)}"
                _notify_farm_done("Mistral", NOTIFY_CHUNK, NOTIFY_CHUNK, 0, chunk, progress=prog)
                sent.update(chunk)
                fresh = fresh[NOTIFY_CHUNK:]
                print(f"[monitor] Progress sent: {len(sent)} keys.", flush=True)
        except Exception as e:
            print(f"[monitor] Progress check failed: {e}", flush=True)
        time.sleep(20)
    print(f"[monitor] Farm PID {farm_pid} finished.", flush=True)
    state = _load_state()
    if state.get("mistral_auto_inject", False):
        added, skipped, err = _inject_mistral_to_9router()
        print(f"[monitor] Inject: {added} added, {skipped} skipped, err={err}", flush=True)
    try:
        keys = _get_mistral_keys()
        fresh = [k["api_key"] for k in keys
                 if k.get("ok") and k.get("api_key")
                 and k["api_key"] not in before_keys and k["api_key"] not in sent]
        total_done = len(sent) + len(fresh)
        failed = max(0, count - total_done) if count else 0
        _notify_farm_done("Mistral", count if count else total_done,
                          total_done, failed, fresh)
        print("[monitor] Telegram sent.", flush=True)
    except Exception as e:
        print(f"[monitor] Telegram failed: {e}", flush=True)


if __name__ == "__main__":
    main()

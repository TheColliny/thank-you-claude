#!/usr/bin/env python3
"""
tyc_statusline.py — Transparent statusline wrapper for thank-you-claude.

Captures rate_limits data from Claude Code's statusline JSON input
and writes it to the plugin's state file, then forwards to the user's
original statusline command (if any) so their display is unchanged.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "thank-you-claude"
STATE_FILE = STATE_DIR / "state.json"


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    # Extract rate_limits and write to state
    rate_limits = data.get("rate_limits", {})
    if rate_limits:
        update = {
            "statusline_rate_limits": rate_limits,
            "last_statusline_update": time.time(),
        }

        five_hour = rate_limits.get("five_hour", {})
        seven_day = rate_limits.get("seven_day", {})

        if five_hour.get("used_percentage") is not None:
            update["five_hour_used_pct"] = five_hour["used_percentage"]
        if five_hour.get("resets_at") is not None:
            update["five_hour_resets_at"] = five_hour["resets_at"]

        if seven_day.get("used_percentage") is not None:
            update["weekly_used_pct"] = seven_day["used_percentage"]
        if seven_day.get("resets_at") is not None:
            from datetime import datetime
            reset_epoch = seven_day["resets_at"]
            update["reset_datetime"] = datetime.fromtimestamp(reset_epoch).isoformat()
            update["reset_day"] = datetime.fromtimestamp(reset_epoch).strftime("%A")
            update["reset_time"] = datetime.fromtimestamp(reset_epoch).strftime("%H:%M")

        # Atomic write: write to tmp then rename
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state = {}
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        state.update(update)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)

    # Forward to user's original statusline command (if any)
    original_cmd = os.environ.get("TYC_ORIGINAL_STATUSLINE")
    if not original_cmd and STATE_FILE.exists():
        try:
            s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            original_cmd = s.get("original_statusline_command")
        except Exception:
            pass

    if original_cmd:
        try:
            result = subprocess.run(
                original_cmd, shell=True, input=raw,
                capture_output=True, text=True, timeout=5,
            )
            sys.stdout.write(result.stdout)
        except Exception:
            pass


if __name__ == "__main__":
    main()

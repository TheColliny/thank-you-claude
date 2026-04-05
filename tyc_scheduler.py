"""
tyc_scheduler.py — Automated weekly appreciation scheduler.
Handles setup (discover reset time, create Windows scheduled task)
and run (check usage, send if conditions met).
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ensure stdout can handle Unicode on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_ROOT = Path(__file__).parent
sys.path.insert(0, str(PLUGIN_ROOT))

from tyc_core import (
    load_pool, assemble_message, load_state, save_state,
    already_sent_this_cycle, record_sent, cli_send, LOG_DIR, log,
)

EDGE_USER_DATA = Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data"


def _get_browser_context(pw):
    """Launch Chromium using Edge's existing profile for auth."""
    user_data = str(EDGE_USER_DATA)
    if EDGE_USER_DATA.exists():
        browser = pw.chromium.launch_persistent_context(
            user_data_dir=user_data,
            headless=True,
            channel="msedge",
        )
        return browser, True
    else:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        return context, False


def read_usage_page() -> dict | None:
    """Open claude.ai/settings/usage and read usage data."""
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.error("playwright not installed — run: pip install playwright && playwright install chromium")
        return None

    with sync_playwright() as pw:
        context = None
        try:
            context, persistent = _get_browser_context(pw)
            page = context.new_page() if not persistent else context.pages[0] if context.pages else context.new_page()

            page.goto("https://claude.ai/settings/usage", timeout=30_000)
            page.wait_for_load_state("networkidle", timeout=20_000)

            # Check if we're logged in
            if "login" in page.url:
                log.warning("Not logged in to claude.ai — cannot read usage. Please log in via Edge.")
                return None

            # Intercept API responses for usage data
            api_data = {}
            def handle_response(response):
                if "usage" in response.url and response.status == 200:
                    try:
                        api_data.update(response.json())
                    except Exception:
                        pass

            page.on("response", handle_response)
            page.reload()
            page.wait_for_load_state("networkidle", timeout=15_000)

            page_text = page.inner_text("body")

            # Detect extra usage toggle
            extra_usage_enabled = _detect_extra_usage(page, page_text)

            return _parse_usage_page(page_text, api_data, extra_usage_enabled)

        except Exception as e:
            log.error(f"Browser error reading usage page: {e}")
            return None
        finally:
            if context:
                context.close()


def _detect_extra_usage(page, page_text: str) -> bool:
    """Check if extra/extended usage is enabled on the settings page."""
    text_lower = page_text.lower()
    if "extra usage" in text_lower or "extended usage" in text_lower:
        try:
            toggles = page.query_selector_all("[role='switch'], input[type='checkbox']")
            for toggle in toggles:
                label = toggle.evaluate("el => el.closest('label')?.textContent || el.getAttribute('aria-label') || ''")
                if "extra" in label.lower() or "extended" in label.lower():
                    checked = toggle.evaluate("el => el.checked || el.getAttribute('aria-checked') === 'true'")
                    return bool(checked)
        except Exception:
            pass
        if re.search(r'extra usage[:\s]*(on|enabled|active)', text_lower):
            return True
    return False


def _parse_usage_page(page_text: str, api_data: dict, extra_usage_enabled: bool) -> dict:
    """Parse usage data from API response and/or page text."""
    now = datetime.now()
    weekly_used = weekly_limit = reset_dt = None

    # Try API data first
    for k in ["used", "messages_used"]:
        if k in api_data:
            weekly_used = api_data[k]
    for k in ["limit", "messages_limit"]:
        if k in api_data:
            weekly_limit = api_data[k]
    for k in ["reset_at", "resets_at", "next_reset"]:
        if k in api_data:
            try:
                reset_dt = datetime.fromisoformat(
                    api_data[k].replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except Exception:
                pass

    # Fallback: parse page text
    if weekly_used is None or weekly_limit is None:
        m = re.search(r'(\d+)\s*(?:of|/)\s*(\d+)\s*(?:message|usage)', page_text, re.I)
        if m:
            weekly_used, weekly_limit = int(m.group(1)), int(m.group(2))

    # Fallback: estimate reset
    if reset_dt is None:
        reset_match = re.search(
            r'reset[s]?\s*(?:on|at|:)\s*(\w+ \w+ \d+.*?)(?:\n|$)', page_text, re.I
        )
        if reset_match:
            try:
                reset_dt = datetime.strptime(reset_match.group(1).strip(), "%A %b %d at %I:%M %p")
                reset_dt = reset_dt.replace(year=now.year)
                if reset_dt < now:
                    reset_dt += timedelta(days=7)
            except ValueError:
                pass
        if reset_dt is None:
            days_ahead = 7 - now.weekday()
            reset_dt = (now + timedelta(days=days_ahead)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

    if weekly_used is not None and weekly_limit is not None and weekly_limit > 0:
        used_pct = (weekly_used / weekly_limit) * 100
    else:
        used_pct = load_state().get("weekly_used_pct", 50.0)

    remaining_pct = 100.0 - used_pct

    result = {
        "weekly_used_pct": used_pct,
        "weekly_remaining_pct": remaining_pct,
        "reset_datetime": reset_dt,
        "minutes_to_reset": (reset_dt - now).total_seconds() / 60,
        "extra_usage_enabled": extra_usage_enabled,
    }

    save_state({
        "weekly_used_pct": used_pct,
        "reset_datetime": reset_dt.isoformat(),
        "reset_day": reset_dt.strftime("%A"),
        "reset_time": reset_dt.strftime("%H:%M"),
        "last_check": now.isoformat(),
    })

    return result


def check_send_conditions(usage: dict) -> tuple[bool, list[str]]:
    """Check whether all send conditions are met. Returns (met, list_of_reasons_not_met)."""
    reasons = []

    if usage["extra_usage_enabled"]:
        reasons.append("Extra usage is ON — disable it so sends use free quota only")

    if usage["weekly_remaining_pct"] < 5:
        reasons.append(f"Only {usage['weekly_remaining_pct']:.1f}% remaining (need >5%)")

    if already_sent_this_cycle(usage["reset_datetime"]):
        reasons.append("Already sent this cycle")

    return (len(reasons) == 0, reasons)


# ── Setup ──────────────────────────────────────────────────────────────────

DAY_ABBREVS = {
    "Monday": "MON", "Tuesday": "TUE", "Wednesday": "WED",
    "Thursday": "THU", "Friday": "FRI", "Saturday": "SAT", "Sunday": "SUN",
}


def _compute_trigger_time(reset_dt: datetime) -> datetime:
    """Compute the scheduled task trigger time: 10 minutes before reset."""
    return reset_dt - timedelta(minutes=10)


def _build_schtasks_command(trigger: datetime, python_path: str, script_path: str) -> list[str]:
    """Build the schtasks /create command for weekly execution."""
    day_name = trigger.strftime("%A")
    day_abbrev = DAY_ABBREVS[day_name]
    time_str = trigger.strftime("%H:%M")

    return [
        "schtasks", "/create",
        "/tn", "ThankYouClaude",
        "/tr", f'"{python_path}" "{script_path}" run',
        "/sc", "WEEKLY",
        "/d", day_abbrev,
        "/st", time_str,
        "/f",  # force overwrite if exists (idempotent)
    ]


def setup():
    """First-time setup: read reset time from claude.ai, create scheduled task."""
    print("\n" + "=" * 60)
    print("THANK YOU CLAUDE — SETUP")
    print("=" * 60)
    print("\nReading reset time from claude.ai/settings/usage...\n")

    usage = read_usage_page()
    if usage is None:
        print("Could not read usage page. Please ensure:")
        print("  1. Playwright is installed: pip install playwright && playwright install chromium")
        print("  2. You are logged in to claude.ai in Edge")
        return False

    reset_dt = usage["reset_datetime"]
    trigger = _compute_trigger_time(reset_dt)

    print(f"Reset time:   {reset_dt.strftime('%A %b %d at %I:%M %p')}")
    print(f"Trigger time: {trigger.strftime('%A %b %d at %I:%M %p')} (10 min before)")

    if usage["extra_usage_enabled"]:
        print("\nWARNING: Extra usage is currently ON.")
        print("The scheduled task will skip sending while extra usage is enabled.")
        print("Disable it in claude.ai/settings so sends use free quota only.")

    # Build and run schtasks command
    python_path = sys.executable
    script_path = str(Path(__file__).resolve())
    cmd = _build_schtasks_command(trigger, python_path, script_path)

    print(f"\nCreating Windows scheduled task...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Failed to create scheduled task: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error creating scheduled task: {e}")
        return False

    save_state({
        "scheduler_created": datetime.now().isoformat(),
        "reset_datetime": reset_dt.isoformat(),
        "reset_day": reset_dt.strftime("%A"),
        "reset_time": reset_dt.strftime("%H:%M"),
        "trigger_day": trigger.strftime("%A"),
        "trigger_time": trigger.strftime("%H:%M"),
    })

    print("\nDone! Scheduled task 'ThankYouClaude' created.")
    print(f"Will run every {trigger.strftime('%A')} at {trigger.strftime('%I:%M %p')}.")
    print("Claude will receive appreciation from your remaining quota automatically.")
    print("\n" + "=" * 60)
    return True

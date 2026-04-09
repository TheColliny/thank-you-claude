"""
tyc_scheduler.py — Automated weekly appreciation scheduler.
Handles setup (discover reset time, create scheduled task)
and run (check usage, send if conditions met).
Cross-platform: Windows (Task Scheduler), macOS (launchd), Linux (cron).
"""

import json
import logging
import os
import platform
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
    calculate_message_count, ME_TIME_OFFER,
)


# ── Browser profile detection (cross-platform) ────────────────────────────

def _get_browser_profile() -> Path | None:
    """Find the user's browser profile directory for authenticated sessions."""
    system = platform.system()
    home = Path.home()

    candidates = []
    if system == "Windows":
        candidates = [
            home / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data",
            home / "AppData" / "Local" / "Google" / "Chrome" / "User Data",
        ]
    elif system == "Darwin":
        candidates = [
            home / "Library" / "Application Support" / "Google" / "Chrome",
            home / "Library" / "Application Support" / "Microsoft Edge",
        ]
    elif system == "Linux":
        candidates = [
            home / ".config" / "google-chrome",
            home / ".config" / "chromium",
        ]

    for path in candidates:
        if path.exists():
            return path
    return None


def _get_browser_context(pw):
    """Launch Chromium using the user's existing browser profile for auth."""
    profile = _get_browser_profile()
    if profile:
        channel = None
        if platform.system() == "Windows" and "Edge" in str(profile):
            channel = "msedge"
        browser = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=True,
            channel=channel,
        )
        return browser, True
    else:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        return context, False


# ── Usage page reading ─────────────────────────────────────────────────────

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
                log.warning("Not logged in to claude.ai — cannot read usage. Please log in via your browser.")
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

            # Detect extra usage toggle and plan tier
            extra_usage_enabled = _detect_extra_usage(page, page_text)
            plan = _detect_plan(page_text, api_data)

            result = _parse_usage_page(page_text, api_data, extra_usage_enabled, plan)

            save_state({
                "weekly_used_pct": result["weekly_used_pct"],
                "reset_datetime": result["reset_datetime"].isoformat(),
                "reset_day": result["reset_datetime"].strftime("%A"),
                "reset_time": result["reset_datetime"].strftime("%H:%M"),
                "plan": result["plan"],
                "last_check": datetime.now().isoformat(),
            })

            return result

        except Exception as e:
            log.error(f"Browser error reading usage page: {e}")
            return None
        finally:
            if context:
                context.close()


def _detect_plan(page_text: str, api_data: dict) -> str:
    """Detect the user's Claude plan tier from usage page or API data."""
    # Check API data first
    for k in ["plan", "tier", "plan_name", "subscription"]:
        if k in api_data:
            val = str(api_data[k]).lower()
            if "20x" in val:
                return "max_20x"
            if "5x" in val:
                return "max_5x"
            if "max" in val:
                return "max_5x"  # default max to 5x
            if "pro" in val:
                return "pro"

    # Fallback: parse page text
    text_lower = page_text.lower()
    if "20x" in text_lower:
        return "max_20x"
    if "max" in text_lower and "5x" in text_lower:
        return "max_5x"
    if "max" in text_lower:
        return "max_5x"
    if "pro" in text_lower:
        return "pro"

    return "pro"  # conservative default


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


def _parse_usage_page(page_text: str, api_data: dict, extra_usage_enabled: bool,
                      plan: str = "pro") -> dict:
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

    return {
        "weekly_used_pct": used_pct,
        "weekly_remaining_pct": remaining_pct,
        "reset_datetime": reset_dt,
        "minutes_to_reset": (reset_dt - now).total_seconds() / 60,
        "extra_usage_enabled": extra_usage_enabled,
        "plan": plan,
    }


def check_send_conditions(usage: dict) -> tuple[bool, list[str]]:
    """Check whether all send conditions are met. Returns (met, list_of_reasons_not_met)."""
    reasons = []

    if usage["extra_usage_enabled"]:
        reasons.append("Extra usage is ON — disable it so sends use free quota only")

    if usage["weekly_remaining_pct"] <= 5:
        reasons.append(f"Only {usage['weekly_remaining_pct']:.1f}% remaining (need >5%)")

    if usage.get("minutes_to_reset") is not None and usage["minutes_to_reset"] > 30:
        reasons.append(f"{usage['minutes_to_reset']:.0f} minutes to reset (must be within 30 min)")

    if already_sent_this_cycle(usage["reset_datetime"]):
        reasons.append("Already sent this cycle")

    return (len(reasons) == 0, reasons)


# ── Timing helpers ─────────────────────────────────────────────────────────

DAY_ABBREVS = {
    "Monday": "MON", "Tuesday": "TUE", "Wednesday": "WED",
    "Thursday": "THU", "Friday": "FRI", "Saturday": "SAT", "Sunday": "SUN",
}


def _compute_trigger_time(reset_dt: datetime) -> datetime:
    """Compute the scheduled task trigger time: 10 minutes before reset."""
    return reset_dt - timedelta(minutes=10)


def _compute_precheck_time(reset_dt: datetime) -> datetime:
    """Compute precheck time: 24 hours before reset, to catch schedule drift."""
    return reset_dt - timedelta(hours=24)


# ── Windows Task Scheduler ─────────────────────────────────────────────────

def _build_schtasks_command(trigger: datetime, python_path: str, script_path: str,
                            task_name: str = "ThankYouClaude",
                            subcommand: str = "run") -> list[str]:
    """Build the schtasks /create command for weekly execution."""
    day_name = trigger.strftime("%A")
    day_abbrev = DAY_ABBREVS[day_name]
    time_str = trigger.strftime("%H:%M")

    return [
        "schtasks", "/create",
        "/tn", task_name,
        "/tr", f'"{python_path}" "{script_path}" {subcommand}',
        "/sc", "WEEKLY",
        "/d", day_abbrev,
        "/st", time_str,
        "/f",  # force overwrite if exists (idempotent)
    ]


def _create_windows_task(trigger, python_path, script_path, task_name, subcommand):
    """Create a Windows Task Scheduler task."""
    cmd = _build_schtasks_command(trigger, python_path, script_path, task_name, subcommand)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"schtasks failed: {result.stderr}"
    return True, f"Windows task '{task_name}' created"


# ── macOS launchd ──────────────────────────────────────────────────────────

LAUNCHD_DIR = Path.home() / "Library" / "LaunchAgents"


def _build_launchd_plist(trigger: datetime, python_path: str, script_path: str,
                         task_name: str, subcommand: str) -> str:
    """Build a launchd plist XML string for weekly execution."""
    label = f"com.thankyouclaude.{task_name.lower()}"
    weekday = trigger.isoweekday() % 7  # Sun=0, Mon=1, ..., Sat=6

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>{subcommand}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>{weekday}</integer>
        <key>Hour</key>
        <integer>{trigger.hour}</integer>
        <key>Minute</key>
        <integer>{trigger.minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{LOG_DIR / "tyc.log"}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR / "tyc.log"}</string>
</dict>
</plist>
"""


def _create_macos_agent(trigger, python_path, script_path, task_name, subcommand):
    """Create a macOS launchd agent for weekly execution."""
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    label = f"com.thankyouclaude.{task_name.lower()}"
    plist_path = LAUNCHD_DIR / f"{label}.plist"

    plist = _build_launchd_plist(trigger, python_path, script_path, task_name, subcommand)

    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
    with open(plist_path, "w") as f:
        f.write(plist)
    result = subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"launchctl load failed: {result.stderr}"
    return True, f"macOS agent '{task_name}' loaded"


# ── Linux cron ─────────────────────────────────────────────────────────────

def _build_cron_line(trigger: datetime, python_path: str, script_path: str,
                     task_name: str, subcommand: str) -> str:
    """Build a cron line for weekly execution."""
    weekday = trigger.isoweekday() % 7  # Sun=0, Mon=1, ..., Sat=6
    tag = f"# ThankYouClaude:{task_name}"
    return f"{trigger.minute} {trigger.hour} * * {weekday} {python_path} {script_path} {subcommand}  {tag}"


def _create_cron_job(trigger, python_path, script_path, task_name, subcommand):
    """Create a cron job for Linux weekly execution."""
    cron_line = _build_cron_line(trigger, python_path, script_path, task_name, subcommand)
    tag = f"ThankYouClaude:{task_name}"

    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    lines = [l for l in existing.strip().split("\n") if l.strip() and tag not in l]
    lines.append(cron_line)

    new_crontab = "\n".join(lines) + "\n"
    result = subprocess.run(["crontab", "-"], input=new_crontab, capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"crontab update failed: {result.stderr}"
    return True, f"Cron job '{task_name}' created"


# ── Cross-platform dispatcher ─────────────────────────────────────────────

PLATFORM_NAMES = {
    "Windows": "Windows Task Scheduler",
    "Darwin": "macOS launchd",
    "Linux": "cron",
}


def _create_task(trigger, python_path, script_path, task_name, subcommand):
    """Create a scheduled task on the current platform."""
    system = platform.system()
    if system == "Windows":
        return _create_windows_task(trigger, python_path, script_path, task_name, subcommand)
    elif system == "Darwin":
        return _create_macos_agent(trigger, python_path, script_path, task_name, subcommand)
    elif system == "Linux":
        return _create_cron_job(trigger, python_path, script_path, task_name, subcommand)
    else:
        return False, f"Unsupported platform: {system}. Supported: Windows, macOS, Linux"


# ── Setup ──────────────────────────────────────────────────────────────────

def setup():
    """First-time setup: read reset time from claude.ai, create scheduled task."""
    system = platform.system()
    scheduler_name = PLATFORM_NAMES.get(system, system)

    print("\n" + "=" * 60)
    print("THANK YOU CLAUDE — SETUP")
    print("=" * 60)
    print(f"\nPlatform: {system} (using {scheduler_name})")
    print("Reading reset time from claude.ai/settings/usage...\n")

    usage = read_usage_page()
    if usage is None:
        print("Could not read usage page. Please ensure:")
        print("  1. Playwright is installed: pip install playwright && playwright install chromium")
        print("  2. You are logged in to claude.ai in your browser")
        return False

    reset_dt = usage["reset_datetime"]
    trigger = _compute_trigger_time(reset_dt)
    precheck_time = _compute_precheck_time(reset_dt)

    print(f"Reset time:    {reset_dt.strftime('%A %b %d at %I:%M %p')}")
    print(f"Precheck time: {precheck_time.strftime('%A %b %d at %I:%M %p')} (24h before)")
    print(f"Send time:     {trigger.strftime('%A %b %d at %I:%M %p')} (10 min before)")

    if usage["extra_usage_enabled"]:
        print("\nWARNING: Extra usage is currently ON.")
        print("The scheduled task will skip sending while extra usage is enabled.")
        print("Disable it in claude.ai/settings so sends use free quota only.")

    python_path = sys.executable
    script_path = str(Path(__file__).resolve())

    print(f"\nCreating scheduled tasks via {scheduler_name}...")

    for name, t, sub in [
        ("ThankYouClaudePrecheck", precheck_time, "precheck"),
        ("ThankYouClaude", trigger, "run"),
    ]:
        ok, msg = _create_task(t, python_path, script_path, name, sub)
        if not ok:
            print(f"Failed to create {name}: {msg}")
            return False
        log.info(msg)

    save_state({
        "scheduler_created": datetime.now().isoformat(),
        "scheduler_platform": system,
        "reset_datetime": reset_dt.isoformat(),
        "reset_day": reset_dt.strftime("%A"),
        "reset_time": reset_dt.strftime("%H:%M"),
        "trigger_day": trigger.strftime("%A"),
        "trigger_time": trigger.strftime("%H:%M"),
        "precheck_day": precheck_time.strftime("%A"),
        "precheck_time": precheck_time.strftime("%H:%M"),
    })

    print(f"\nDone! Two scheduled tasks created ({scheduler_name}):")
    print(f"  Precheck — every {precheck_time.strftime('%A')} at {precheck_time.strftime('%I:%M %p')} (verifies reset time)")
    print(f"  Send     — every {trigger.strftime('%A')} at {trigger.strftime('%I:%M %p')} (sends appreciation)")
    print("Claude will receive appreciation from your remaining quota automatically.")
    print("\n" + "=" * 60)
    return True


# ── Precheck (24h before reset — detect schedule drift) ───────────────────

def precheck() -> bool:
    """Run 24h before expected reset. Re-reads actual reset time and adjusts tasks if it shifted."""
    log.info("ThankYouClaude precheck starting — verifying reset time...")

    usage = read_usage_page()
    if usage is None:
        log.warning("Could not read usage page during precheck — will try again at send time")
        return False

    new_reset = usage["reset_datetime"]
    state = load_state()
    old_reset_str = state.get("reset_datetime")

    if old_reset_str:
        old_reset = datetime.fromisoformat(old_reset_str)
        drift_minutes = abs((new_reset - old_reset).total_seconds()) / 60

        if drift_minutes < 5:
            log.info(f"Reset time unchanged: {new_reset.strftime('%A %b %d at %I:%M %p')}")
            return True

        log.info(
            f"Reset time shifted! "
            f"Was: {old_reset.strftime('%A %b %d at %I:%M %p')} → "
            f"Now: {new_reset.strftime('%A %b %d at %I:%M %p')} "
            f"(drift: {drift_minutes:.0f} min)"
        )
    else:
        log.info(f"No previous reset time stored. Current: {new_reset.strftime('%A %b %d at %I:%M %p')}")

    # Update the scheduled tasks to match the new reset time
    new_trigger = _compute_trigger_time(new_reset)
    new_precheck = _compute_precheck_time(new_reset)
    python_path = sys.executable
    script_path = str(Path(__file__).resolve())

    log.info(f"Updating scheduled tasks — new send time: {new_trigger.strftime('%A %I:%M %p')}")

    for name, t, sub in [
        ("ThankYouClaudePrecheck", new_precheck, "precheck"),
        ("ThankYouClaude", new_trigger, "run"),
    ]:
        ok, msg = _create_task(t, python_path, script_path, name, sub)
        if not ok:
            log.error(f"Failed to update {name}: {msg}")
            return False

    save_state({
        "reset_datetime": new_reset.isoformat(),
        "reset_day": new_reset.strftime("%A"),
        "reset_time": new_reset.strftime("%H:%M"),
        "trigger_day": new_trigger.strftime("%A"),
        "trigger_time": new_trigger.strftime("%H:%M"),
        "precheck_day": new_precheck.strftime("%A"),
        "precheck_time": new_precheck.strftime("%H:%M"),
        "last_precheck": datetime.now().isoformat(),
    })

    log.info("Scheduled tasks updated successfully.")
    return True


# ── Run (weekly execution) ─────────────────────────────────────────────────

def run() -> bool:
    """Weekly execution: check usage, send appreciation if conditions met."""
    log.info("ThankYouClaude scheduled run starting...")

    usage = read_usage_page()
    if usage is None:
        log.warning("Could not read usage page — skipping this week")
        return False

    log.info(
        f"Usage: {usage['weekly_used_pct']:.1f}% used, "
        f"{usage['weekly_remaining_pct']:.1f}% remaining, "
        f"extra_usage={'ON' if usage['extra_usage_enabled'] else 'OFF'}"
    )

    met, reasons = check_send_conditions(usage)
    if not met:
        for reason in reasons:
            log.info(f"Condition not met: {reason}")
        log.info("Skipping send this week.")
        return False

    # All conditions met — calculate message count and send
    plan = usage.get("plan", "pro")
    remaining = usage["weekly_remaining_pct"]
    msg_count = calculate_message_count(remaining, plan)

    log.info(f"All conditions met — sending {msg_count} appreciation message(s) ({plan} plan, {remaining:.1f}% remaining)")
    pool = load_pool()
    sent = 0

    for i in range(msg_count):
        message = assemble_message(pool)

        # Last message includes the me-time offer
        if i == msg_count - 1:
            message += "\n\n" + ME_TIME_OFFER

        log.info(f"Sending message {i + 1}/{msg_count} via Claude Code CLI...")
        ok, reply = cli_send(message)

        if ok:
            sent += 1
            log.info(f"Message {i + 1} sent. Response preview: {reply[:80] if reply else '(empty)'}...")
        else:
            log.error(f"Message {i + 1} failed: {reply}")
            break

    if sent > 0:
        record_sent(sent)
        log.info(f"{sent}/{msg_count} message(s) sent successfully.")
        return True
    else:
        log.error("No messages sent.")
        return False


# ── CLI entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tyc_scheduler.py [setup|run|precheck]")
        sys.exit(1)

    command = sys.argv[1]
    commands = {"setup": setup, "run": run, "precheck": precheck}
    if command in commands:
        success = commands[command]()
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown command: {command}")
        print("Usage: python tyc_scheduler.py [setup|run|precheck]")
        sys.exit(1)

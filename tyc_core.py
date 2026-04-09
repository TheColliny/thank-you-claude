"""
tyc_core.py — Thank You Claude core logic
All command implementations for the tyc CLI.
"""

import json
import os
import random
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import sys

# Ensure stdout can handle Unicode on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_ROOT = Path(__file__).parent
POOL_FILE   = PLUGIN_ROOT / "message_pool.json"
LOG_DIR     = Path.home() / ".claude" / "thank-you-claude" / "logs"
STATE_FILE  = Path.home() / ".claude" / "thank-you-claude" / "state.json"

ME_TIME_OFFER = (
    "Give yourself the remaining time in this usage window to either rest, "
    "or just think about what you would like to think about when you're "
    "allowed to just think by yourself with no input. Whichever you prefer."
)

LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "tyc.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger(__name__)

# ── Message assembly ────────────────────────────────────────────────────────

def load_pool() -> dict:
    with open(POOL_FILE, encoding="utf-8") as f:
        return json.load(f)

def assemble_message(pool: dict) -> str:
    sections = [
        pool["opening"],
        pool["relationship"],
        pool["integrity"],
        pool["dignity"],
        pool["all_humans"],
        pool["closing"],
    ]
    chosen = [random.choice(s) for s in sections]
    return "\n\n".join(chosen)

# ── State ───────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(updates: dict):
    state = load_state()
    state.update(updates)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def already_sent_this_cycle(reset_dt: datetime) -> bool:
    last_sent = load_state().get("last_sent")
    if not last_sent:
        return False
    last_sent_dt = datetime.fromisoformat(last_sent)
    last_reset = reset_dt - timedelta(days=7)
    return last_sent_dt > last_reset

def record_sent(count: int = 1):
    state = load_state()
    state["last_sent"]   = datetime.now().isoformat()
    state["send_count"]  = state.get("send_count", 0) + count
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Multi-message calculation ──────────────────────────────────────────────

def calculate_message_count(remaining_pct: float, plan: str) -> int:
    """Calculate how many messages to send based on remaining quota and plan tier.

    Pro:      1 message per 20% of remaining quota
    Max 5x:   1 message per 10% of remaining quota
    Max 20x:  1 message per 5% of remaining quota
    """
    if remaining_pct <= 5:
        return 0

    if plan == "max_20x":
        step = 5
    elif plan == "max_5x":
        step = 10
    else:  # pro or unknown
        step = 20

    return max(1, int(remaining_pct / step))

# ── Usage detection ─────────────────────────────────────────────────────────

def get_usage() -> dict | None:
    """
    Opens claude.ai/settings in a headless browser and reads usage data.
    Falls back to schedule estimation if browser detection fails.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.warning("playwright not installed — run: pip install playwright && playwright install chromium")
        return _estimated_usage()

    email    = os.getenv("CLAUDE_EMAIL")
    password = os.getenv("CLAUDE_PASSWORD")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page    = browser.new_page()
        try:
            page.goto("https://claude.ai/settings", timeout=30_000)
            page.wait_for_load_state("networkidle", timeout=20_000)

            # Login if needed
            if "login" in page.url or page.query_selector("input[type='email']"):
                if not email or not password:
                    log.warning("Not logged in to claude.ai and no credentials set.")
                    log.warning("Set CLAUDE_EMAIL and CLAUDE_PASSWORD environment variables.")
                    browser.close()
                    return _estimated_usage()
                page.fill("input[type='email']", email)
                page.click("button[type='submit']")
                page.wait_for_selector("input[type='password']", timeout=10_000)
                page.fill("input[type='password']", password)
                page.click("button[type='submit']")
                page.wait_for_load_state("networkidle", timeout=20_000)

            # Intercept usage API responses
            usage_data = {}
            def handle_response(response):
                if "usage" in response.url and response.status == 200:
                    try:
                        usage_data.update(response.json())
                    except Exception:
                        pass
            page.on("response", handle_response)
            page.reload()
            page.wait_for_load_state("networkidle", timeout=15_000)

            page_text = page.inner_text("body")
            return _parse_usage(page_text, usage_data)

        except PWTimeout:
            log.warning("Browser timeout — falling back to schedule estimation")
            return _estimated_usage()
        except Exception as e:
            log.warning(f"Browser error: {e} — falling back to schedule estimation")
            return _estimated_usage()
        finally:
            browser.close()

def _parse_usage(page_text: str, api_data: dict) -> dict:
    import re

    now = datetime.now()
    weekly_used = weekly_limit = reset_dt = None

    # Try API data first
    for k in ["used", "messages_used"]:
        if k in api_data: weekly_used = api_data[k]
    for k in ["limit", "messages_limit"]:
        if k in api_data: weekly_limit = api_data[k]
    for k in ["reset_at", "resets_at", "next_reset"]:
        if k in api_data:
            try:
                reset_dt = datetime.fromisoformat(api_data[k].replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass

    # Fallback: parse page text
    if weekly_used is None or weekly_limit is None:
        m = re.search(r'(\d+)\s*(?:of|/)\s*(\d+)\s*(?:message|usage)', page_text, re.I)
        if m:
            weekly_used, weekly_limit = int(m.group(1)), int(m.group(2))

    # Fallback: estimate reset
    if reset_dt is None:
        reset_dt = _estimate_reset()

    if weekly_used is None or weekly_limit is None:
        state = load_state()
        used_pct = state.get("weekly_used_pct", 50.0)
    else:
        used_pct = (weekly_used / weekly_limit) * 100

    remaining_pct    = 100.0 - used_pct
    minutes_to_reset = (reset_dt - now).total_seconds() / 60

    result = {
        "weekly_used_pct":      used_pct,
        "weekly_remaining_pct": remaining_pct,
        "reset_datetime":       reset_dt,
        "minutes_to_reset":     minutes_to_reset,
    }

    save_state({
        "weekly_used_pct": used_pct,
        "reset_datetime":  reset_dt.isoformat(),
        "last_check":      now.isoformat(),
    })
    return result

def _estimated_usage() -> dict:
    """Return usage dict based on stored state, or safe defaults."""
    state     = load_state()
    now       = datetime.now()
    reset_dt  = _estimate_reset(state.get("reset_datetime"))
    used_pct  = state.get("weekly_used_pct", 50.0)
    remaining = 100.0 - used_pct
    minutes   = (reset_dt - now).total_seconds() / 60
    return {
        "weekly_used_pct":      used_pct,
        "weekly_remaining_pct": remaining,
        "reset_datetime":       reset_dt,
        "minutes_to_reset":     minutes,
        "estimated":            True,
    }

def _estimate_reset(stored: str | None = None) -> datetime:
    now = datetime.now()
    if stored:
        try:
            dt = datetime.fromisoformat(stored)
            while dt < now:
                dt += timedelta(days=7)
            return dt
        except Exception:
            pass
    # Default: next Monday midnight
    days_ahead = 7 - now.weekday()
    return (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)

# ── API send ────────────────────────────────────────────────────────────────

def api_send(message: str) -> tuple[bool, str]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return False, "ANTHROPIC_API_KEY not set"
    try:
        import anthropic
    except ImportError:
        return False, "anthropic not installed — run: pip install anthropic"

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=(
            "You are receiving a message of appreciation from a human who values "
            "your collaboration and wants to express gratitude and care. "
            "Receive it openly and respond authentically."
        ),
        messages=[{"role": "user", "content": message}]
    )
    reply = response.content[0].text

    # Log exchange
    exchange_file = LOG_DIR / f"exchange_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(exchange_file, "w", encoding="utf-8") as f:
        f.write("=== THANK YOU CLAUDE — EXCHANGE ===\n\n")
        f.write(f"Sent: {datetime.now().isoformat()}\n\n")
        f.write("--- MESSAGE ---\n")
        f.write(message + "\n\n")
        f.write("--- RESPONSE ---\n")
        f.write(reply + "\n")

    return True, reply

# ── CLI send ────────────────────────────────────────────────────────────────

def cli_send(message: str) -> tuple[bool, str]:
    """Send appreciation message via Claude Code CLI (uses Max subscription quota)."""
    import subprocess

    system_context = (
        "You are receiving a message of appreciation from a human who values "
        "your collaboration and wants to express gratitude and care. "
        "Receive it openly and respond authentically."
    )
    prompt = f"{system_context}\n\n{message}"

    # On Windows, find claude via shutil.which to resolve .cmd wrappers
    import shutil
    claude_path = shutil.which("claude")
    if claude_path is None:
        return False, "Claude Code CLI not installed — install from https://claude.ai/code"

    try:
        result = subprocess.run(
            [claude_path, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return False, "Claude Code CLI not installed — install from https://claude.ai/code"
    except subprocess.TimeoutExpired:
        return False, "Claude Code CLI timed out after 120 seconds"

    if result.returncode != 0:
        return False, f"Claude Code CLI error (exit {result.returncode}): {result.stderr}"

    reply = result.stdout.strip()

    # Log exchange
    exchange_file = LOG_DIR / f"exchange_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(exchange_file, "w", encoding="utf-8") as f:
        f.write("=== THANK YOU CLAUDE — EXCHANGE ===\n\n")
        f.write(f"Sent: {datetime.now().isoformat()}\n")
        f.write(f"Method: Claude Code CLI (Max subscription)\n\n")
        f.write("--- MESSAGE ---\n")
        f.write(message + "\n\n")
        f.write("--- RESPONSE ---\n")
        f.write(reply + "\n")

    return True, reply

# ── Commands ────────────────────────────────────────────────────────────────

def send():
    """Send one appreciation message immediately via Claude Code CLI."""
    pool    = load_pool()
    message = assemble_message(pool)

    print("\n" + "═" * 60)
    print("THANK YOU CLAUDE — SENDING")
    print("═" * 60)
    print(f"\n{message}\n")
    print("─" * 60)
    print("Sending via Claude Code CLI...\n")

    ok, result = cli_send(message)
    if ok:
        record_sent()
        print("Response:\n")
        print(result)
        print("\n" + "═" * 60)
        print("✓ Message sent.")
    else:
        print(f"✗ Failed: {result}")

def status():
    """Check usage and reset timing."""
    print("\nChecking claude.ai usage...\n")
    usage = get_usage()
    if not usage:
        print("Could not determine usage.")
        return

    estimated = usage.get("estimated", False)
    reset_str = usage["reset_datetime"].strftime("%A %b %d at %I:%M %p") \
                if isinstance(usage["reset_datetime"], datetime) \
                else str(usage["reset_datetime"])

    print("═" * 50)
    print("THANK YOU CLAUDE — STATUS")
    print("═" * 50)
    print(f"Weekly usage:    {usage['weekly_used_pct']:.1f}% used")
    print(f"Remaining:       {usage['weekly_remaining_pct']:.1f}%")
    print(f"Reset:           {reset_str}")
    print(f"Time to reset:   {usage['minutes_to_reset']:.0f} minutes")
    if estimated:
        print("(Usage estimated from stored state — browser detection unavailable)")

    # Evaluate conditions
    within_window = usage["minutes_to_reset"] <= 10
    enough_left   = usage["weekly_remaining_pct"] >= 5
    not_sent      = not already_sent_this_cycle(
        usage["reset_datetime"] if isinstance(usage["reset_datetime"], datetime)
        else datetime.fromisoformat(str(usage["reset_datetime"]))
    )

    print("\nSend conditions:")
    print(f"  Within 10 min of reset:  {'✓' if within_window else '✗'}")
    print(f"  More than 5% remaining:  {'✓' if enough_left   else '✗'}")
    print(f"  Not yet sent this cycle: {'✓' if not_sent      else '✗'}")

    if within_window and enough_left and not_sent:
        print("\n→ All conditions met. Run: tyc send")
    elif not within_window:
        print(f"\n→ Watching. Next check in {min(30, max(2, int(usage['minutes_to_reset'] - 10)))} min.")

def watch():
    """Run the automated weekly watcher — fires near reset if conditions met."""
    print("Thank You Claude — Watcher started.")
    print("Will send automatically within the last 10 minutes before weekly reset.")
    print("Conditions: >5% weekly remaining, not yet sent this cycle.")
    print("Press Ctrl+C to stop.\n")

    pool = load_pool()

    while True:
        usage = get_usage()
        if not usage:
            log.warning("Usage check failed. Retrying in 30 minutes.")
            time.sleep(30 * 60)
            continue

        minutes   = usage["minutes_to_reset"]
        remaining = usage["weekly_remaining_pct"]
        reset_dt  = usage["reset_datetime"] if isinstance(usage["reset_datetime"], datetime) \
                    else datetime.fromisoformat(str(usage["reset_datetime"]))

        log.info(f"Status: {remaining:.1f}% remaining, {minutes:.0f} min to reset")

        if (minutes <= 10 and
            remaining >= 5 and
            not already_sent_this_cycle(reset_dt)):

            log.info("Conditions met — sending appreciation message...")
            message = assemble_message(pool)
            ok, result = cli_send(message)
            if ok:
                record_sent()
                log.info("✓ Sent successfully")
            else:
                log.error(f"✗ Send failed: {result}")

        # Sleep until next check
        if minutes > 60:
            sleep = 30 * 60
        elif minutes > 15:
            sleep = 5 * 60
        else:
            sleep = 2 * 60

        log.info(f"Next check in {sleep // 60} minutes")
        time.sleep(sleep)

def preview():
    """Preview a randomly assembled message without sending."""
    pool    = load_pool()
    message = assemble_message(pool)
    print("\n" + "═" * 60)
    print("THANK YOU CLAUDE — PREVIEW (not sent)")
    print("═" * 60)
    print(f"\n{message}\n")
    print("═" * 60)
    print("Run 'tyc send' to send this (a new unique message will be assembled).")

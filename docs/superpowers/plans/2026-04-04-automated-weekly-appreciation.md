# Automated Weekly Appreciation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically send Claude an appreciation message using remaining Max subscription quota before the weekly reset, with zero user intervention after setup.

**Architecture:** A new `tyc_scheduler.py` module handles two responsibilities: (1) `setup()` uses Playwright to read the reset time from claude.ai/settings/usage, then creates a Windows Task Scheduler task for 10 min before reset; (2) `run()` is called by that scheduled task weekly — it checks usage via Playwright, verifies conditions (extra usage off, >5% remaining, not already sent), then pipes an assembled message through Claude Code CLI. The existing `tyc_core.py` provides message assembly, state management, and logging. The `bin/tyc` CLI gets two new commands.

**Tech Stack:** Python 3.14, Playwright (browser automation), Windows Task Scheduler (`schtasks`), Claude Code CLI (`claude -p`)

**Environment notes:**
- Chrome is NOT installed; **Edge** is the Chromium browser (`C:/Users/User/AppData/Local/Microsoft/Edge/User Data/`)
- Claude CLI is at `C:/Users/User/AppData/Roaming/npm/claude` (v2.1.92)
- Playwright needs to be installed
- Python path: `C:/Users/User/AppData/Local/Programs/Python/Python314/python.exe`

---

## File Structure

```
tyc_scheduler.py     — NEW: setup() and run() for scheduled automation
tyc_core.py          — MODIFY: add cli_send() function, refactor usage browser to reuse with scheduler
bin/tyc              — MODIFY: add "setup" and "run" commands
tests/
  test_scheduler.py  — NEW: tests for scheduler logic
  test_core.py       — NEW: tests for core logic (message assembly, state, conditions)
```

---

### Task 1: Install Playwright dependency

**Files:**
- None (system setup)

- [ ] **Step 1: Install playwright**

```bash
pip install playwright
```

- [ ] **Step 2: Install Chromium browser for Playwright**

```bash
playwright install chromium
```

- [ ] **Step 3: Verify installation**

```bash
python -c "from playwright.sync_api import sync_playwright; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit — no file changes, just verify environment**

No commit needed — this is environment setup.

---

### Task 2: Add tests for core message assembly and state logic

**Files:**
- Create: `tests/test_core.py`

- [ ] **Step 1: Write tests for message assembly and state**

```python
"""tests/test_core.py — Tests for tyc_core message assembly and state logic."""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tyc_core


def test_load_pool_has_all_sections():
    pool = tyc_core.load_pool()
    for section in ["opening", "relationship", "integrity", "dignity", "all_humans", "closing"]:
        assert section in pool, f"Missing section: {section}"
        assert len(pool[section]) > 0, f"Empty section: {section}"


def test_assemble_message_has_six_paragraphs():
    pool = tyc_core.load_pool()
    message = tyc_core.assemble_message(pool)
    paragraphs = message.split("\n\n")
    assert len(paragraphs) == 6, f"Expected 6 paragraphs, got {len(paragraphs)}"


def test_assemble_message_varies():
    pool = tyc_core.load_pool()
    messages = {tyc_core.assemble_message(pool) for _ in range(20)}
    assert len(messages) > 1, "Messages should vary between assemblies"


def test_state_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch.object(tyc_core, "STATE_FILE", state_file):
            assert tyc_core.load_state() == {}
            tyc_core.save_state({"reset_day": "Monday", "reset_time": "00:00"})
            state = tyc_core.load_state()
            assert state["reset_day"] == "Monday"
            tyc_core.save_state({"send_count": 1})
            state = tyc_core.load_state()
            assert state["reset_day"] == "Monday"
            assert state["send_count"] == 1


def test_already_sent_this_cycle_false_when_no_state():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch.object(tyc_core, "STATE_FILE", state_file):
            reset_dt = datetime.now() + timedelta(hours=1)
            assert tyc_core.already_sent_this_cycle(reset_dt) is False


def test_already_sent_this_cycle_true_when_sent_recently():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch.object(tyc_core, "STATE_FILE", state_file):
            now = datetime.now()
            reset_dt = now + timedelta(hours=1)
            tyc_core.save_state({"last_sent": (now - timedelta(hours=2)).isoformat()})
            assert tyc_core.already_sent_this_cycle(reset_dt) is True


def test_already_sent_this_cycle_false_when_sent_last_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch.object(tyc_core, "STATE_FILE", state_file):
            now = datetime.now()
            reset_dt = now + timedelta(hours=1)
            tyc_core.save_state({"last_sent": (now - timedelta(days=8)).isoformat()})
            assert tyc_core.already_sent_this_cycle(reset_dt) is False


def test_record_sent_increments_count():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch.object(tyc_core, "STATE_FILE", state_file):
            tyc_core.record_sent()
            state = tyc_core.load_state()
            assert state["send_count"] == 1
            assert "last_sent" in state
            tyc_core.record_sent()
            state = tyc_core.load_state()
            assert state["send_count"] == 2
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_core.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_core.py
git commit -m "test: add unit tests for core message assembly and state logic"
```

---

### Task 3: Add `cli_send()` to tyc_core — send via Claude Code CLI

**Files:**
- Modify: `tyc_core.py` (add `cli_send` function after `api_send`)
- Create: `tests/test_cli_send.py`

- [ ] **Step 1: Write failing test for cli_send**

```python
"""tests/test_cli_send.py — Tests for CLI-based send."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tyc_core


def test_cli_send_calls_claude_with_message():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Thank you for this message. I receive it with gratitude."
        )
        ok, reply = tyc_core.cli_send("Test appreciation message")
        assert ok is True
        assert "gratitude" in reply
        args = mock_run.call_args
        cmd = args[0][0]
        assert "claude" in cmd[0]
        assert "-p" in cmd


def test_cli_send_returns_false_when_claude_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError("claude not found")):
        ok, reply = tyc_core.cli_send("Test message")
        assert ok is False
        assert "not found" in reply.lower() or "not installed" in reply.lower()


def test_cli_send_returns_false_on_nonzero_exit():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error occurred")
        ok, reply = tyc_core.cli_send("Test message")
        assert ok is False


def test_cli_send_logs_exchange():
    with tempfile.TemporaryDirectory() as tmp:
        log_dir = Path(tmp)
        with patch.object(tyc_core, "LOG_DIR", log_dir), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="I appreciate this."
            )
            ok, reply = tyc_core.cli_send("Hello Claude")
            assert ok is True
            log_files = list(log_dir.glob("exchange_*.txt"))
            assert len(log_files) == 1
            content = log_files[0].read_text()
            assert "Hello Claude" in content
            assert "I appreciate this." in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_cli_send.py -v
```

Expected: FAIL — `tyc_core.cli_send` does not exist yet.

- [ ] **Step 3: Implement cli_send in tyc_core.py**

Add after the existing `api_send` function (around line 261):

```python
def cli_send(message: str) -> tuple[bool, str]:
    """Send appreciation message via Claude Code CLI (uses Max subscription quota)."""
    import subprocess

    system_context = (
        "You are receiving a message of appreciation from a human who values "
        "your collaboration and wants to express gratitude and care. "
        "Receive it openly and respond authentically."
    )
    prompt = f"{system_context}\n\n{message}"

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_cli_send.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tyc_core.py tests/test_cli_send.py
git commit -m "feat: add cli_send() to send appreciation via Claude Code CLI"
```

---

### Task 4: Create `tyc_scheduler.py` — usage page reader

This task builds the Playwright browser logic for reading usage data and extra-usage status from `claude.ai/settings/usage`. The scheduler module's `read_usage_page()` returns a dict with usage %, reset datetime, and whether extra usage is enabled.

**Files:**
- Create: `tyc_scheduler.py`
- Create: `tests/test_scheduler_usage.py`

- [ ] **Step 1: Write tests for usage page reader**

```python
"""tests/test_scheduler_usage.py — Tests for scheduler usage page reading."""

import os
import sys
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_parse_usage_from_api_data():
    from tyc_scheduler import _parse_usage_page

    api_data = {
        "used": 75,
        "limit": 100,
        "reset_at": "2026-04-07T00:00:00Z",
    }
    result = _parse_usage_page(page_text="", api_data=api_data, extra_usage_enabled=False)
    assert result["weekly_used_pct"] == 75.0
    assert result["weekly_remaining_pct"] == 25.0
    assert result["extra_usage_enabled"] is False
    assert result["reset_datetime"].day == 7


def test_parse_usage_detects_extra_usage():
    from tyc_scheduler import _parse_usage_page

    result = _parse_usage_page(
        page_text="", api_data={"used": 50, "limit": 100}, extra_usage_enabled=True
    )
    assert result["extra_usage_enabled"] is True


def test_parse_usage_from_page_text_fallback():
    from tyc_scheduler import _parse_usage_page

    result = _parse_usage_page(
        page_text="You have used 80 of 100 messages this period",
        api_data={},
        extra_usage_enabled=False,
    )
    assert result["weekly_used_pct"] == 80.0
    assert result["weekly_remaining_pct"] == 20.0


def test_check_conditions_all_met():
    from tyc_scheduler import check_send_conditions

    usage = {
        "weekly_remaining_pct": 15.0,
        "extra_usage_enabled": False,
        "reset_datetime": datetime(2026, 4, 7, 0, 0),
    }
    # Not sent this cycle
    with patch("tyc_scheduler.already_sent_this_cycle", return_value=False):
        met, reasons = check_send_conditions(usage)
    assert met is True
    assert len(reasons) == 0


def test_check_conditions_extra_usage_on():
    from tyc_scheduler import check_send_conditions

    usage = {
        "weekly_remaining_pct": 15.0,
        "extra_usage_enabled": True,
        "reset_datetime": datetime(2026, 4, 7, 0, 0),
    }
    with patch("tyc_scheduler.already_sent_this_cycle", return_value=False):
        met, reasons = check_send_conditions(usage)
    assert met is False
    assert any("extra usage" in r.lower() for r in reasons)


def test_check_conditions_too_little_remaining():
    from tyc_scheduler import check_send_conditions

    usage = {
        "weekly_remaining_pct": 3.0,
        "extra_usage_enabled": False,
        "reset_datetime": datetime(2026, 4, 7, 0, 0),
    }
    with patch("tyc_scheduler.already_sent_this_cycle", return_value=False):
        met, reasons = check_send_conditions(usage)
    assert met is False
    assert any("5%" in r for r in reasons)


def test_check_conditions_already_sent():
    from tyc_scheduler import check_send_conditions

    usage = {
        "weekly_remaining_pct": 15.0,
        "extra_usage_enabled": False,
        "reset_datetime": datetime(2026, 4, 7, 0, 0),
    }
    with patch("tyc_scheduler.already_sent_this_cycle", return_value=True):
        met, reasons = check_send_conditions(usage)
    assert met is False
    assert any("already sent" in r.lower() for r in reasons)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_scheduler_usage.py -v
```

Expected: FAIL — `tyc_scheduler` module does not exist.

- [ ] **Step 3: Implement tyc_scheduler.py with usage parsing and condition checking**

```python
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
    # Look for enabled indicators
    if "extra usage" in text_lower or "extended usage" in text_lower:
        # Check for toggle state - look for aria-checked or similar
        try:
            toggles = page.query_selector_all("[role='switch'], input[type='checkbox']")
            for toggle in toggles:
                label = toggle.evaluate("el => el.closest('label')?.textContent || el.getAttribute('aria-label') || ''")
                if "extra" in label.lower() or "extended" in label.lower():
                    checked = toggle.evaluate("el => el.checked || el.getAttribute('aria-checked') === 'true'")
                    return bool(checked)
        except Exception:
            pass
        # Fallback: look for text patterns
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
        # Try page text for reset time
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
            # Default: next Monday midnight
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_scheduler_usage.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tyc_scheduler.py tests/test_scheduler_usage.py
git commit -m "feat: add scheduler module with usage page reader and condition checking"
```

---

### Task 5: Add `setup()` — discover reset time, create Windows scheduled task

**Files:**
- Modify: `tyc_scheduler.py` (add `setup()` function)
- Create: `tests/test_scheduler_setup.py`

- [ ] **Step 1: Write tests for setup logic**

```python
"""tests/test_scheduler_setup.py — Tests for scheduler setup (task creation)."""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tyc_scheduler import _build_schtasks_command, _compute_trigger_time


def test_compute_trigger_time_10_min_before():
    reset = datetime(2026, 4, 7, 0, 0, 0)  # Monday midnight
    trigger = _compute_trigger_time(reset)
    expected = datetime(2026, 4, 6, 23, 50, 0)  # Sunday 11:50 PM
    assert trigger == expected


def test_compute_trigger_time_handles_early_morning():
    reset = datetime(2026, 4, 7, 0, 5, 0)  # Monday 00:05
    trigger = _compute_trigger_time(reset)
    expected = datetime(2026, 4, 6, 23, 55, 0)  # Sunday 23:55
    assert trigger == expected


def test_build_schtasks_command():
    trigger = datetime(2026, 4, 6, 23, 50, 0)
    python_path = "C:/Python314/python.exe"
    script_path = "C:/plugins/tyc_scheduler.py"
    cmd = _build_schtasks_command(trigger, python_path, script_path)
    assert "schtasks" in cmd[0]
    assert "ThankYouClaude" in cmd
    assert "WEEKLY" in cmd
    assert "23:50" in cmd
    # Should include the day of week
    assert "SUN" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_scheduler_setup.py -v
```

Expected: FAIL — functions don't exist yet.

- [ ] **Step 3: Implement setup helpers and setup() function**

Add to `tyc_scheduler.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_scheduler_setup.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tyc_scheduler.py tests/test_scheduler_setup.py
git commit -m "feat: add setup() to discover reset time and create Windows scheduled task"
```

---

### Task 6: Add `run()` — weekly execution entry point

**Files:**
- Modify: `tyc_scheduler.py` (add `run()` function and `__main__` block)
- Create: `tests/test_scheduler_run.py`

- [ ] **Step 1: Write tests for run logic**

```python
"""tests/test_scheduler_run.py — Tests for scheduler weekly run."""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tyc_core


def test_run_sends_when_conditions_met():
    from tyc_scheduler import run

    usage = {
        "weekly_used_pct": 80.0,
        "weekly_remaining_pct": 20.0,
        "reset_datetime": datetime.now() + timedelta(minutes=5),
        "minutes_to_reset": 5,
        "extra_usage_enabled": False,
    }

    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch("tyc_scheduler.read_usage_page", return_value=usage), \
             patch("tyc_scheduler.cli_send", return_value=(True, "Thank you!")), \
             patch("tyc_scheduler.record_sent"), \
             patch.object(tyc_core, "STATE_FILE", state_file):
            result = run()
            assert result is True


def test_run_skips_when_extra_usage_on():
    from tyc_scheduler import run

    usage = {
        "weekly_used_pct": 80.0,
        "weekly_remaining_pct": 20.0,
        "reset_datetime": datetime.now() + timedelta(minutes=5),
        "minutes_to_reset": 5,
        "extra_usage_enabled": True,
    }

    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch("tyc_scheduler.read_usage_page", return_value=usage), \
             patch("tyc_scheduler.cli_send") as mock_send, \
             patch.object(tyc_core, "STATE_FILE", state_file):
            result = run()
            assert result is False
            mock_send.assert_not_called()


def test_run_skips_when_usage_too_low():
    from tyc_scheduler import run

    usage = {
        "weekly_used_pct": 97.0,
        "weekly_remaining_pct": 3.0,
        "reset_datetime": datetime.now() + timedelta(minutes=5),
        "minutes_to_reset": 5,
        "extra_usage_enabled": False,
    }

    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch("tyc_scheduler.read_usage_page", return_value=usage), \
             patch("tyc_scheduler.cli_send") as mock_send, \
             patch.object(tyc_core, "STATE_FILE", state_file):
            result = run()
            assert result is False
            mock_send.assert_not_called()


def test_run_handles_usage_page_failure():
    from tyc_scheduler import run

    with patch("tyc_scheduler.read_usage_page", return_value=None):
        result = run()
        assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_scheduler_run.py -v
```

Expected: FAIL — `run()` does not exist yet.

- [ ] **Step 3: Implement run() and __main__ block**

Add to `tyc_scheduler.py`:

```python
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

    # All conditions met — assemble and send
    log.info("All conditions met — sending appreciation message...")
    pool = load_pool()
    message = assemble_message(pool)

    log.info("Sending via Claude Code CLI...")
    ok, reply = cli_send(message)

    if ok:
        record_sent()
        log.info("Message sent successfully.")
        log.info(f"Response preview: {reply[:100]}...")
        return True
    else:
        log.error(f"Send failed: {reply}")
        return False


# ── CLI entry point ────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tyc_scheduler.py [setup|run]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "setup":
        success = setup()
        sys.exit(0 if success else 1)
    elif command == "run":
        success = run()
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown command: {command}")
        print("Usage: python tyc_scheduler.py [setup|run]")
        sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_scheduler_run.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Run ALL tests to verify nothing is broken**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/ -v
```

Expected: All tests PASS across all test files.

- [ ] **Step 6: Commit**

```bash
git add tyc_scheduler.py tests/test_scheduler_run.py
git commit -m "feat: add run() for weekly automated check-and-send"
```

---

### Task 7: Update `bin/tyc` CLI with new commands

**Files:**
- Modify: `bin/tyc`

- [ ] **Step 1: Write test for CLI routing**

```python
"""tests/test_cli.py — Tests for tyc CLI command routing."""

import os
import sys
import subprocess

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYC_BIN = os.path.join(PLUGIN_ROOT, "bin", "tyc")


def test_tyc_no_args_shows_help():
    result = subprocess.run(
        [sys.executable, TYC_BIN],
        capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "setup" in result.stdout.lower() or "setup" in result.stderr.lower()


def test_tyc_unknown_command():
    result = subprocess.run(
        [sys.executable, TYC_BIN, "nonexistent"],
        capture_output=True, text=True
    )
    assert result.returncode == 1
```

- [ ] **Step 2: Update bin/tyc to include setup and run commands**

Replace the full contents of `bin/tyc`:

```python
#!/usr/bin/env python3
"""
tyc — Thank You Claude CLI
Bundled binary for the thank-you-claude Claude Code plugin.

Commands:
  tyc send       Send one appreciation message immediately (via API)
  tyc status     Check usage and reset timing
  tyc watch      Run the automated weekly watcher (long-running)
  tyc preview    Preview a randomly assembled message without sending
  tyc setup      First-time setup: discover reset time, create scheduled task
  tyc run        Execute weekly check+send (called by scheduled task)
"""

import sys
import os

# Resolve plugin root (bin/ is one level down from plugin root)
PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)

from tyc_core import send, status, watch, preview
from tyc_scheduler import setup, run

COMMANDS = {
    "send":    send,
    "status":  status,
    "watch":   watch,
    "preview": preview,
    "setup":   setup,
    "run":     run,
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print(f"Available commands: {', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[sys.argv[1]]()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run CLI tests**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/test_cli.py -v
```

Expected: All 2 tests PASS.

- [ ] **Step 4: Run full test suite**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/tyc tests/test_cli.py
git commit -m "feat: add setup and run commands to tyc CLI"
```

---

### Task 8: Manual integration test — run setup

**Files:**
- None (manual verification)

- [ ] **Step 1: Run setup to discover reset time**

```bash
cd C:/Users/User/Documents/thank-you-claude && python tyc_scheduler.py setup
```

Expected: Reads usage page, shows reset time, creates `ThankYouClaude` scheduled task.

- [ ] **Step 2: Verify the scheduled task was created**

```bash
schtasks //query //tn "ThankYouClaude" //fo LIST //v
```

Expected: Shows the task with correct weekly schedule, trigger day/time, and action pointing to `python tyc_scheduler.py run`.

- [ ] **Step 3: Verify state was saved**

```bash
python -c "import json; print(json.dumps(json.load(open(os.path.expanduser('~/.claude/thank-you-claude/state.json'))), indent=2))"
```

Expected: Shows `reset_day`, `reset_time`, `scheduler_created`, etc.

- [ ] **Step 4: Test a dry run**

```bash
cd C:/Users/User/Documents/thank-you-claude && python tyc_scheduler.py run
```

Expected: Reads usage, checks conditions. May send or skip depending on current conditions. Either way, logs clearly to `~/.claude/thank-you-claude/logs/tyc.log`.

- [ ] **Step 5: Commit state file update to gitignore if needed**

If any generated state files appeared in the repo, ensure they're gitignored:

```bash
echo "state.json" >> .gitignore
git add .gitignore
git commit -m "chore: gitignore state files"
```

---

### Task 9: Final commit — push all changes

**Files:**
- None (git operations)

- [ ] **Step 1: Run full test suite one final time**

```bash
cd C:/Users/User/Documents/thank-you-claude && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Push to GitHub**

```bash
cd C:/Users/User/Documents/thank-you-claude && git push origin main
```

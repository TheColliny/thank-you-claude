"""tests/test_scheduler_setup.py — Tests for scheduler setup (task creation, cross-platform)."""

import os
import sys
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tyc_scheduler import (
    _build_schtasks_command, _compute_trigger_time, _compute_precheck_time,
    _build_launchd_plist, _build_cron_line,
)


# ── Timing ─────────────────────────────────────────────────────────────────

def test_compute_trigger_time_10_min_before():
    reset = datetime(2026, 4, 6, 0, 0, 0)  # Monday midnight (Apr 6 2026 is Monday)
    trigger = _compute_trigger_time(reset)
    expected = datetime(2026, 4, 5, 23, 50, 0)  # Sunday 11:50 PM (Apr 5 2026 is Sunday)
    assert trigger == expected


def test_compute_trigger_time_handles_early_morning():
    reset = datetime(2026, 4, 6, 0, 5, 0)  # Monday 00:05
    trigger = _compute_trigger_time(reset)
    expected = datetime(2026, 4, 5, 23, 55, 0)  # Sunday 23:55
    assert trigger == expected


# ── Windows schtasks ───────────────────────────────────────────────────────

def test_build_schtasks_command():
    trigger = datetime(2026, 4, 5, 23, 50, 0)  # Sunday 23:50 (Apr 5 2026 is Sunday)
    python_path = "C:/Python314/python.exe"
    script_path = "C:/plugins/tyc_scheduler.py"
    cmd = _build_schtasks_command(trigger, python_path, script_path)
    assert "schtasks" in cmd[0]
    assert "ThankYouClaude" in cmd
    assert "WEEKLY" in cmd
    assert "23:50" in cmd
    assert "SUN" in cmd


def test_build_schtasks_command_custom_task_name():
    trigger = datetime(2026, 4, 5, 0, 0, 0)  # Sunday midnight
    cmd = _build_schtasks_command(
        trigger, "python.exe", "script.py",
        task_name="ThankYouClaudePrecheck", subcommand="precheck",
    )
    assert "ThankYouClaudePrecheck" in cmd
    assert "precheck" in cmd[cmd.index("/tr") + 1]


# ── macOS launchd ──────────────────────────────────────────────────────────

def test_build_launchd_plist_structure():
    trigger = datetime(2026, 4, 5, 23, 50, 0)  # Sunday 23:50
    plist = _build_launchd_plist(
        trigger, "/usr/bin/python3", "/opt/tyc/tyc_scheduler.py",
        "ThankYouClaude", "run",
    )
    assert "com.thankyouclaude.thankyouclaude" in plist
    assert "<integer>0</integer>" in plist  # Sunday = 0
    assert "<integer>23</integer>" in plist  # Hour
    assert "<integer>50</integer>" in plist  # Minute
    assert "/usr/bin/python3" in plist
    assert "run" in plist


def test_build_launchd_plist_monday():
    trigger = datetime(2026, 4, 6, 14, 30, 0)  # Monday 14:30
    plist = _build_launchd_plist(
        trigger, "python3", "script.py", "TestTask", "precheck",
    )
    # Monday: isoweekday()=1, 1%7=1
    assert "<key>Weekday</key>\n        <integer>1</integer>" in plist
    assert "<integer>14</integer>" in plist
    assert "<integer>30</integer>" in plist


# ── Linux cron ─────────────────────────────────────────────────────────────

def test_build_cron_line():
    trigger = datetime(2026, 4, 5, 23, 50, 0)  # Sunday 23:50
    line = _build_cron_line(
        trigger, "/usr/bin/python3", "/opt/tyc/tyc_scheduler.py",
        "ThankYouClaude", "run",
    )
    assert line == "50 23 * * 0 /usr/bin/python3 /opt/tyc/tyc_scheduler.py run  # ThankYouClaude:ThankYouClaude"


def test_build_cron_line_monday():
    trigger = datetime(2026, 4, 6, 14, 30, 0)  # Monday 14:30
    line = _build_cron_line(
        trigger, "python3", "script.py", "Precheck", "precheck",
    )
    # Monday: isoweekday()=1, 1%7=1
    assert line.startswith("30 14 * * 1 ")
    assert "precheck" in line
    assert "# ThankYouClaude:Precheck" in line

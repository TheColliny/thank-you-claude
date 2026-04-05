"""tests/test_scheduler_setup.py — Tests for scheduler setup (task creation)."""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tyc_scheduler import _build_schtasks_command, _compute_trigger_time, _compute_precheck_time


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

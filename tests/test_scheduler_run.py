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

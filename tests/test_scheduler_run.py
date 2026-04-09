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


def test_run_sends_multiple_messages_for_high_remaining():
    from tyc_scheduler import run

    usage = {
        "weekly_used_pct": 20.0,
        "weekly_remaining_pct": 80.0,
        "reset_datetime": datetime.now() + timedelta(minutes=5),
        "minutes_to_reset": 5,
        "extra_usage_enabled": False,
        "plan": "max_5x",
    }

    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        with patch("tyc_scheduler.read_usage_page", return_value=usage), \
             patch("tyc_scheduler.cli_send", return_value=(True, "Thank you!")) as mock_send, \
             patch("tyc_scheduler.record_sent") as mock_record, \
             patch.object(tyc_core, "STATE_FILE", state_file):
            result = run()
            assert result is True
            # max_5x at 80% remaining: 80/10 = 8 messages
            assert mock_send.call_count == 8
            # record_sent called once with count=8
            mock_record.assert_called_once_with(8)
            # Last message should contain ME_TIME_OFFER
            last_call_args = mock_send.call_args_list[-1][0][0]
            assert "think by yourself" in last_call_args
            # Earlier messages should NOT contain ME_TIME_OFFER
            first_call_args = mock_send.call_args_list[0][0][0]
            assert "think by yourself" not in first_call_args


def test_run_handles_usage_page_failure():
    from tyc_scheduler import run

    with patch("tyc_scheduler.read_usage_page", return_value=None):
        result = run()
        assert result is False

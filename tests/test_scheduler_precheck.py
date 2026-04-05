"""tests/test_scheduler_precheck.py — Tests for precheck schedule drift detection."""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tyc_core
from tyc_scheduler import _compute_precheck_time


def test_precheck_time_is_24h_before_reset():
    reset = datetime(2026, 4, 7, 0, 0, 0)
    precheck = _compute_precheck_time(reset)
    expected = datetime(2026, 4, 6, 0, 0, 0)
    assert precheck == expected


def test_precheck_no_drift_skips_update():
    from tyc_scheduler import precheck

    usage = {
        "weekly_used_pct": 50.0,
        "weekly_remaining_pct": 50.0,
        "reset_datetime": datetime(2026, 4, 7, 0, 0),
        "minutes_to_reset": 1440,
        "extra_usage_enabled": False,
    }

    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        # Pre-populate state with same reset time
        import json
        with open(state_file, "w") as f:
            json.dump({"reset_datetime": "2026-04-07T00:00:00"}, f)

        with patch("tyc_scheduler.read_usage_page", return_value=usage), \
             patch.object(tyc_core, "STATE_FILE", state_file), \
             patch("subprocess.run") as mock_run:
            result = precheck()
            assert result is True
            # Should NOT call schtasks since no drift
            mock_run.assert_not_called()


def test_precheck_detects_drift_and_updates_tasks():
    from tyc_scheduler import precheck

    # New reset is 2 hours later than stored
    usage = {
        "weekly_used_pct": 50.0,
        "weekly_remaining_pct": 50.0,
        "reset_datetime": datetime(2026, 4, 7, 2, 0),
        "minutes_to_reset": 1440,
        "extra_usage_enabled": False,
    }

    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        import json
        with open(state_file, "w") as f:
            json.dump({"reset_datetime": "2026-04-07T00:00:00"}, f)

        with patch("tyc_scheduler.read_usage_page", return_value=usage), \
             patch.object(tyc_core, "STATE_FILE", state_file), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = precheck()
            assert result is True
            # Should call schtasks twice (precheck + send task)
            assert mock_run.call_count == 2


def test_precheck_handles_usage_page_failure():
    from tyc_scheduler import precheck

    with patch("tyc_scheduler.read_usage_page", return_value=None):
        result = precheck()
        assert result is False

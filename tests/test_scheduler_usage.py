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

"""tests/test_statusline.py — Tests for statusline wrapper integration."""

import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tyc_core


def test_get_usage_from_state_with_data():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        state = {
            "weekly_used_pct": 75.0,
            "reset_datetime": "2026-04-18T17:00:00",
            "five_hour_used_pct": 30.0,
            "last_statusline_update": time.time(),
            "plan": "max_5x",
        }
        state_file.write_text(json.dumps(state), encoding="utf-8")

        with patch.object(tyc_core, "STATE_FILE", state_file):
            usage = tyc_core.get_usage_from_state()
            assert usage is not None
            assert usage["weekly_used_pct"] == 75.0
            assert usage["weekly_remaining_pct"] == 25.0
            assert usage["five_hour_used_pct"] == 30.0
            assert usage["plan"] == "max_5x"
            assert usage["source"] == "statusline"


def test_get_usage_from_state_no_data():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        state_file.write_text("{}", encoding="utf-8")

        with patch.object(tyc_core, "STATE_FILE", state_file):
            usage = tyc_core.get_usage_from_state()
            assert usage is None


def test_install_statusline_fresh():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        state_file = Path(tmp) / "state.json"
        settings_file.write_text("{}", encoding="utf-8")

        with patch.object(tyc_core, "CLAUDE_SETTINGS", settings_file), \
             patch.object(tyc_core, "STATE_FILE", state_file):
            result = tyc_core.install_statusline()
            assert result is True

            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            assert "statusLine" in settings
            assert "tyc_statusline" in settings["statusLine"]["command"]


def test_install_statusline_preserves_original():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        state_file = Path(tmp) / "state.json"
        settings_file.write_text(json.dumps({
            "statusLine": {"type": "command", "command": "my-custom-statusline.sh"}
        }), encoding="utf-8")

        with patch.object(tyc_core, "CLAUDE_SETTINGS", settings_file), \
             patch.object(tyc_core, "STATE_FILE", state_file):
            result = tyc_core.install_statusline()
            assert result is True

            # Original should be saved in state
            state = json.loads(state_file.read_text(encoding="utf-8"))
            assert state["original_statusline_command"] == "my-custom-statusline.sh"

            # Settings should have our wrapper
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            assert "tyc_statusline" in settings["statusLine"]["command"]


def test_uninstall_statusline_restores_original():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        state_file = Path(tmp) / "state.json"

        # State has original command saved
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({
            "original_statusline_command": "my-custom-statusline.sh"
        }), encoding="utf-8")

        # Settings has our wrapper
        settings_file.write_text(json.dumps({
            "statusLine": {"type": "command", "command": "python tyc_statusline.py"}
        }), encoding="utf-8")

        with patch.object(tyc_core, "CLAUDE_SETTINGS", settings_file), \
             patch.object(tyc_core, "STATE_FILE", state_file):
            result = tyc_core.uninstall_statusline()
            assert result is True

            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            assert settings["statusLine"]["command"] == "my-custom-statusline.sh"


def test_uninstall_statusline_removes_when_no_original():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        state_file = Path(tmp) / "state.json"

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{}", encoding="utf-8")

        settings_file.write_text(json.dumps({
            "statusLine": {"type": "command", "command": "python tyc_statusline.py"}
        }), encoding="utf-8")

        with patch.object(tyc_core, "CLAUDE_SETTINGS", settings_file), \
             patch.object(tyc_core, "STATE_FILE", state_file):
            result = tyc_core.uninstall_statusline()
            assert result is True

            settings = json.loads(settings_file.read_text(encoding="utf-8"))
            assert "statusLine" not in settings

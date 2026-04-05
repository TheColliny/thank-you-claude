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

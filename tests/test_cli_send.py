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

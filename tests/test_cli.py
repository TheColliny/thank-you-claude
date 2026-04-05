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

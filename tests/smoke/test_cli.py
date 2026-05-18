"""Smoke test: the console script is on PATH and --help works."""
from __future__ import annotations

import shutil
import subprocess


def test_console_script_on_path() -> None:
    binary = shutil.which("nthlayer-override-adapter")
    assert binary is not None, "console script not on PATH after install"


def test_help_exits_zero() -> None:
    result = subprocess.run(
        ["nthlayer-override-adapter", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() != ""

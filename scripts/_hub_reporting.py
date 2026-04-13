"""Report BBG pipeline results back into automation-hub's status.json.

Usage at the bottom of a BBG script:

    if __name__ == "__main__":
        from _hub_reporting import reporting
        with reporting("pull_earnings.py", changes=["earnings refreshed"]):
            main()

The context manager times the block, invokes automation-hub's
`scripts.hub_report` CLI on exit (success or failure), and swallows any
reporting errors so they never mask the underlying pipeline result.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path


HUB_DIR = Path(os.environ.get("AUTOMATION_HUB_DIR", r"C:\Users\AdrianOw\Projects\automation-hub"))
PROJECT = "bbg"


def _invoke(args: list[str]) -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "scripts.hub_report", *args],
            cwd=str(HUB_DIR),
            check=False,
            timeout=120,
        )
    except Exception:
        traceback.print_exc()


@contextlib.contextmanager
def reporting(script_label: str, changes: list[str] | None = None):
    """Report the wrapped block's result to automation-hub on exit."""
    started = time.time()
    try:
        yield
    except BaseException as exc:
        duration = int(time.time() - started)
        _invoke([
            PROJECT,
            "--status", "failed",
            "--message", f"{script_label}: {exc}",
            "--duration", str(duration),
        ])
        raise
    else:
        duration = int(time.time() - started)
        args = [
            PROJECT,
            "--status", "success",
            "--message", f"{script_label} completed",
            "--duration", str(duration),
        ]
        for change in (changes or [f"{script_label} ran"]):
            args.extend(["--change", change])
        _invoke(args)

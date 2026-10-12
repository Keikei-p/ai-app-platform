"""Window-safe options for Aivy subprocesses.

Windows can flash a console for each Node/Python test/build invocation,
especially from GUI/automated workers. This keeps the same argv,
time limits, captured logs and return codes, without spawning an extra shell.
"""
from __future__ import annotations

import os
import subprocess
from typing import Any


def quiet_process_options(platform: str | None = None) -> dict[str, Any]:
    """Hide only child console windows on Windows; preserve all other behavior."""
    kind = os.name if platform is None else platform
    if kind != "nt":
        return {}

    # CREATE_NO_WINDOW prevents console processes from allocating a new console
    # when launched from pythonw.exe/Tkinter and other no-console parents.
    options: dict[str, Any] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    }
    startup_cls = getattr(subprocess, "STARTUPINFO", None)
    if startup_cls is not None:
        startupinfo = startup_cls()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        options["startupinfo"] = startupinfo
    return options

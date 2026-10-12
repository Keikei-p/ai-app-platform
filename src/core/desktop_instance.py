"""Single-instance protection for the local Aivy desktop GUI.

A second double-click must not start a second Tk worker pool, independently
scheduled self-drive loop, or duplicate local build attempt. Windows named
mutex ownership automatically disappears after app exit/crash.
"""
from __future__ import annotations

import ctypes
import os
from contextlib import contextmanager
from typing import Iterator

_MUTEX_NAME = r"Local\AivyDesktopInteractiveSession"
_ERROR_ALREADY_EXISTS = 183


@contextmanager
def desktop_instance_lock() -> Iterator[bool]:
    """Yield False for the second concurrent GUI in the current Windows session.

    Only a GUI entry point uses this lock. The web server, CLI tests, installed
    workspaces, and database are untouched. No process is force-killed.
    """
    if os.name != "nt":
        yield True
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    create_mutex.restype = ctypes.c_void_p
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (ctypes.c_void_p,)
    close_handle.restype = ctypes.c_bool

    handle = create_mutex(None, False, _MUTEX_NAME)
    if not handle:
        raise OSError(ctypes.get_last_error(), "Aivy desktop instance mutex failed")
    already_running = ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
    try:
        yield not already_running
    finally:
        close_handle(handle)

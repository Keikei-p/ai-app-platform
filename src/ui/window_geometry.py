"""Keep the initial client area inside the desktop work area (including taskbar)."""
import ctypes
import os
from ctypes import wintypes


def work_area(root):
    if os.name == "nt":
        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def fit_geometry(area, preferred=(1140, 760)):
    left, top, width, height = area
    # Reserve space for window decorations and DPI-scaled title bars.
    w = max(1, min(preferred[0], width - 48))
    h = max(1, min(preferred[1], height - 100))
    return f"{w}x{h}+{left + 16}+{top + 16}"

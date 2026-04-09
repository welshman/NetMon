"""
utils.py — Shared utility helpers (gateway discovery, formatting).
"""

import re
import socket
import subprocess
import sys


def get_default_gateway() -> str:
    """Return the default gateway IP address."""
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["ipconfig"], text=True, stderr=subprocess.DEVNULL, timeout=5
            )
            # Find "Default Gateway . . . . . . . . . : x.x.x.x"
            m = re.search(r"Default Gateway[\s.]+:\s*([\d.]+)", out)
            if m:
                return m.group(1)
        else:
            out = subprocess.check_output(
                ["ip", "route", "show", "default"],
                text=True, stderr=subprocess.DEVNULL, timeout=5
            )
            m = re.search(r"default via ([\d.]+)", out)
            if m:
                return m.group(1)
    except Exception:
        pass
    # Fallback: use socket routing trick
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            # Gateway is usually .1 of the local subnet
            local = s.getsockname()[0]
            parts = local.rsplit(".", 1)
            return parts[0] + ".1"
    except Exception:
        return "192.168.1.1"


def fmt_ms(val) -> str:
    """Format a latency value for display."""
    if val is None:
        return "  ----"
    return f"{val:6.1f}"


def fmt_pct(val: float) -> str:
    return f"{val:5.1f}%"


def bytes_human(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

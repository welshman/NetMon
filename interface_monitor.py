"""
interface_monitor.py — Detect active NIC, link speed, and WiFi metrics.
Uses psutil for cross-platform NIC stats and netsh (Windows) for WiFi.
"""

import platform
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Optional

import psutil

import logger

REFRESH_SECS = 10


@dataclass
class InterfaceInfo:
    name: str = ""
    is_wifi: bool = False
    ipv4: str = ""
    # Ethernet
    speed_mbps: Optional[int] = None
    is_up: bool = True
    # WiFi (Windows netsh / Linux iw)
    ssid: str = ""
    signal_dbm: Optional[int] = None
    signal_quality: str = ""
    channel: str = ""
    frequency: str = ""
    noise_dbm: Optional[int] = None
    # Misc
    bytes_sent: int = 0
    bytes_recv: int = 0


def _get_default_interface() -> str:
    """Return the NIC name used for the default route."""
    try:
        # Connect to a public IP (no data sent) to find local outbound interface
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]

        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address == local_ip:
                    return iface
    except Exception:
        pass
    return ""


def _wifi_info_windows(iface: str) -> dict:
    """Query netsh wlan for WiFi statistics on Windows."""
    info = {}
    try:
        out = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"],
            stderr=subprocess.DEVNULL, text=True, timeout=10
        )
    except Exception:
        return info

    # netsh output is key : value pairs
    for line in out.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if "ssid" in key and "bssid" not in key:
            info["ssid"] = val
        elif "signal" in key:
            # "Signal : 78%"
            info["signal_quality"] = val
            # Convert % → dBm (approx: dBm = (quality/2) - 100)
            m = re.search(r"(\d+)", val)
            if m:
                q = int(m.group(1))
                info["signal_dbm"] = int((q / 2) - 100)
        elif "channel" in key:
            info["channel"] = val
        elif "radio type" in key:
            info["frequency"] = val
    return info


def _wifi_info_linux(iface: str) -> dict:
    """Query iwconfig for WiFi stats on Linux."""
    info = {}
    try:
        out = subprocess.check_output(
            ["iwconfig", iface], stderr=subprocess.DEVNULL, text=True, timeout=5
        )
    except Exception:
        return info

    ssid_m = re.search(r'ESSID:"([^"]+)"', out)
    if ssid_m:
        info["ssid"] = ssid_m.group(1)
    sig_m = re.search(r"Signal level[=: ]+(-?\d+)\s*dBm", out)
    if sig_m:
        info["signal_dbm"] = int(sig_m.group(1))
    noise_m = re.search(r"Noise level[=: ]+(-?\d+)\s*dBm", out)
    if noise_m:
        info["noise_dbm"] = int(noise_m.group(1))
    freq_m = re.search(r"Frequency:(\S+)", out)
    if freq_m:
        info["frequency"] = freq_m.group(1)
    return info


class InterfaceMonitor:
    """Polls interface statistics in a background thread."""

    def __init__(self):
        self.info = InterfaceInfo()
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self):
        self._refresh()  # Populate immediately
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(REFRESH_SECS):
            self._refresh()

    def _refresh(self):
        iface = _get_default_interface()
        self.info.name = iface

        # Determine if WiFi
        is_wifi = False
        if sys.platform == "win32":
            is_wifi = iface.lower().startswith("wi-fi") or "wifi" in iface.lower() or "wireless" in iface.lower()
        else:
            is_wifi = iface.lower().startswith(("wlan", "wlp", "wl0"))
        self.info.is_wifi = is_wifi

        # IP address
        addrs = psutil.net_if_addrs().get(iface, [])
        for addr in addrs:
            if addr.family == socket.AF_INET:
                self.info.ipv4 = addr.address
                break

        # Link stats
        stats = psutil.net_if_stats().get(iface)
        if stats:
            self.info.is_up = stats.isup
            self.info.speed_mbps = stats.speed  # 0 = unknown

        # IO counters
        io = psutil.net_io_counters(pernic=True).get(iface)
        if io:
            self.info.bytes_sent = io.bytes_sent
            self.info.bytes_recv = io.bytes_recv

        # WiFi extras
        if is_wifi:
            if sys.platform == "win32":
                w = _wifi_info_windows(iface)
            else:
                w = _wifi_info_linux(iface)
            self.info.ssid = w.get("ssid", "")
            self.info.signal_dbm = w.get("signal_dbm")
            self.info.signal_quality = w.get("signal_quality", "")
            self.info.channel = w.get("channel", "")
            self.info.frequency = w.get("frequency", "")
            self.info.noise_dbm = w.get("noise_dbm")

        logger.log_interface({
            "interface": self.info.name,
            "type": "WiFi" if self.info.is_wifi else "Ethernet",
            "ip": self.info.ipv4,
            "speed_mbps": self.info.speed_mbps,
            "ssid": self.info.ssid,
            "signal_dbm": self.info.signal_dbm,
            "signal_quality": self.info.signal_quality,
            "channel": self.info.channel,
        })

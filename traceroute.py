"""
traceroute.py — Periodic traceroute snapshots to detect path changes.
"""

import re
import subprocess
import sys
import time
from threading import Event, Thread

import logger

DEFAULT_INTERVAL_SECS = 300  # run traceroute every 5 minutes


def _run_traceroute(target: str) -> list[str]:
    """Run OS traceroute and return parsed hop lines."""
    if sys.platform == "win32":
        cmd = ["tracert", "-d", "-h", "20", "-w", "1000", target]
    else:
        cmd = ["traceroute", "-n", "-m", "20", "-w", "1", target]

    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                      timeout=60, text=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return ["[traceroute unavailable]"]

    hops = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip header lines
        if re.match(r"^(Tracing|traceroute|over|\d+ hops)", line, re.IGNORECASE):
            continue
        hops.append(line)
    return hops or ["[no hops returned]"]


class TracerouteMonitor:
    """Runs traceroute snapshots in a background thread."""

    def __init__(self, targets: list[str], interval: int = DEFAULT_INTERVAL_SECS):
        self.targets = targets
        self.interval = interval
        self._stop = Event()
        self._thread: Thread | None = None
        self.last_hops: dict[str, list[str]] = {}

    def start(self):
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        # Run immediately at start, then on interval
        self._run_all()
        while not self._stop.wait(self.interval):
            self._run_all()

    def _run_all(self):
        for target in self.targets:
            hops = _run_traceroute(target)
            prev = self.last_hops.get(target)
            if prev is not None and prev != hops:
                logger.log_alert(f"ROUTE CHANGE detected for {target}")
            self.last_hops[target] = hops
            logger.log_traceroute(target, hops)

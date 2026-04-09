"""
ping_monitor.py — ICMP ping loop for latency, jitter, and packet-loss tracking.
Uses subprocess to call the OS ping utility — no raw sockets needed.
"""

import re
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Event, Thread
from typing import Optional

import logger

# Rolling window size for jitter / loss calculations
WINDOW = 60


@dataclass
class PingStats:
    target: str
    latencies: deque = field(default_factory=lambda: deque(maxlen=WINDOW))
    sent: int = 0
    lost: int = 0
    last_latency: Optional[float] = None
    last_jitter: float = 0.0
    consecutive_timeouts: int = 0
    alert_threshold_ms: float = 150.0
    loss_alert_threshold_pct: float = 5.0

    @property
    def avg_latency(self) -> Optional[float]:
        return sum(self.latencies) / len(self.latencies) if self.latencies else None

    @property
    def packet_loss_pct(self) -> float:
        return (self.lost / self.sent * 100) if self.sent else 0.0

    @property
    def jitter(self) -> float:
        if len(self.latencies) < 2:
            return 0.0
        diffs = [abs(self.latencies[i] - self.latencies[i - 1])
                 for i in range(1, len(self.latencies))]
        return sum(diffs) / len(diffs)

    @property
    def min_latency(self) -> Optional[float]:
        return min(self.latencies) if self.latencies else None

    @property
    def max_latency(self) -> Optional[float]:
        return max(self.latencies) if self.latencies else None


def _ping_once(host: str) -> Optional[float]:
    """Send one ICMP echo and return latency in ms, or None on timeout."""
    if sys.platform == "win32":
        cmd = ["ping", "-n", "1", "-w", "2000", host]
    else:
        cmd = ["ping", "-c", "1", "-W", "2", host]

    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                      timeout=5, text=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
            FileNotFoundError):
        return None

    # Windows: "time=12ms" or "time<1ms"
    # Linux/macOS: "time=12.3 ms"
    match = re.search(r"time[=<](\d+\.?\d*)\s*ms", out, re.IGNORECASE)
    if match:
        return float(match.group(1))
    # Windows "<1ms" edge-case
    if re.search(r"time<1ms", out, re.IGNORECASE):
        return 0.5
    return None


class PingMonitor:
    """Runs continuous ping loops in background threads."""

    def __init__(self, targets: list[str], interval: float = 1.0):
        self.targets = targets
        self.interval = interval
        self.stats: dict[str, PingStats] = {t: PingStats(target=t) for t in targets}
        self._stop = Event()
        self._threads: list[Thread] = []

    def start(self):
        for target in self.targets:
            t = Thread(target=self._loop, args=(target,), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stop.set()

    def _loop(self, target: str):
        stats = self.stats[target]
        while not self._stop.is_set():
            tick = time.monotonic()
            latency = _ping_once(target)
            stats.sent += 1

            if latency is None:
                stats.lost += 1
                stats.consecutive_timeouts += 1
                logger.log_csv("PING_TIMEOUT", target=target,
                               packet_loss_pct=stats.packet_loss_pct)
                if stats.consecutive_timeouts == 3:
                    msg = f"TIMEOUT x3: {target} is not responding (3 consecutive timeouts)"
                    logger.log_alert(msg)
            else:
                stats.consecutive_timeouts = 0
                prev = stats.last_latency
                stats.last_latency = latency
                stats.latencies.append(latency)

                jitter_now = abs(latency - prev) if prev is not None else 0.0
                stats.last_jitter = jitter_now

                logger.log_csv("PING", target=target, latency_ms=latency,
                               packet_loss_pct=stats.packet_loss_pct,
                               jitter_ms=stats.jitter)

                # Alert checks
                if latency > stats.alert_threshold_ms:
                    logger.log_alert(
                        f"HIGH LATENCY: {target} {latency:.1f}ms "
                        f"(threshold {stats.alert_threshold_ms:.0f}ms)"
                    )
                if jitter_now > 50:
                    logger.log_alert(
                        f"HIGH JITTER SPIKE: {target} jitter={jitter_now:.1f}ms"
                    )

            if stats.sent % WINDOW == 0 and stats.sent > 0:
                loss = stats.packet_loss_pct
                if loss >= stats.loss_alert_threshold_pct:
                    logger.log_alert(
                        f"PACKET LOSS: {target} {loss:.1f}% over last {WINDOW} samples"
                    )

            elapsed = time.monotonic() - tick
            sleep_for = max(0.0, self.interval - elapsed)
            self._stop.wait(sleep_for)

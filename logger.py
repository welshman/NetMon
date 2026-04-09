"""
logger.py — Session logging for NetMon.
Creates a new TXT + CSV log file every session.
"""

import csv
import os
from datetime import datetime

SESSION_START = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_DIR = "logs"


def _ensure_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _txt_path() -> str:
    return os.path.join(LOG_DIR, f"session_{SESSION_START}.txt")


def _csv_path() -> str:
    return os.path.join(LOG_DIR, f"session_{SESSION_START}.csv")


# ── CSV setup ──────────────────────────────────────────────────────────────────
_CSV_HEADERS = [
    "timestamp", "event", "target", "latency_ms",
    "packet_loss_pct", "jitter_ms", "ttl", "detail"
]
_csv_file = None
_csv_writer = None


def _init_csv():
    global _csv_file, _csv_writer
    _ensure_dir()
    _csv_file = open(_csv_path(), "w", newline="", encoding="utf-8")
    _csv_writer = csv.DictWriter(_csv_file, fieldnames=_CSV_HEADERS)
    _csv_writer.writeheader()
    _csv_file.flush()


def log_txt(message: str, level: str = "INFO"):
    """Append a timestamped line to the TXT log."""
    _ensure_dir()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level:8s}] {message}\n"
    with open(_txt_path(), "a", encoding="utf-8") as f:
        f.write(line)


def log_csv(event: str, target: str = "", latency_ms: float = None,
            packet_loss_pct: float = None, jitter_ms: float = None,
            ttl: int = None, detail: str = ""):
    """Append a structured row to the CSV log."""
    global _csv_file, _csv_writer
    if _csv_writer is None:
        _init_csv()
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event": event,
        "target": target,
        "latency_ms": f"{latency_ms:.2f}" if latency_ms is not None else "",
        "packet_loss_pct": f"{packet_loss_pct:.1f}" if packet_loss_pct is not None else "",
        "jitter_ms": f"{jitter_ms:.2f}" if jitter_ms is not None else "",
        "ttl": ttl if ttl is not None else "",
        "detail": detail,
    }
    _csv_writer.writerow(row)
    _csv_file.flush()


def log_session_header(gateway: str, targets: list, interface: str):
    """Write the session banner to the TXT log."""
    sep = "=" * 70
    log_txt(sep)
    log_txt("  NetMon — Network Stability Monitor")
    log_txt(f"  Session started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_txt(f"  Gateway          : {gateway}")
    log_txt(f"  External targets : {', '.join(targets)}")
    log_txt(f"  Interface        : {interface}")
    log_txt(sep)
    _init_csv()


def log_session_footer(summary: dict):
    """Write session summary to TXT log and flush CSV."""
    global _csv_file
    sep = "=" * 70
    log_txt(sep)
    log_txt("  SESSION SUMMARY")
    log_txt(sep)
    for key, val in summary.items():
        log_txt(f"  {key:<30} {val}")
    log_txt(sep)
    if _csv_file:
        _csv_file.close()


def log_alert(message: str):
    log_txt(message, level="ALERT")
    log_csv("ALERT", detail=message)


def log_traceroute(target: str, hops: list):
    """Write a traceroute snapshot to the TXT log."""
    log_txt(f"--- Traceroute to {target} ---")
    for hop in hops:
        log_txt(f"  {hop}")
    log_csv("TRACEROUTE", target=target, detail=f"{len(hops)} hops")


def log_interface(info: dict):
    """Write interface stats to TXT log."""
    log_txt("--- Interface Stats ---")
    for k, v in info.items():
        log_txt(f"  {k}: {v}")
    log_csv("INTERFACE", detail=str(info))

"""
main.py — Entry point for NetMon.
Starts all monitors and drives the live console dashboard.

Usage:
    python main.py
    python main.py --interval 2 --targets 8.8.8.8 1.1.1.1
    python main.py --config config.json
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime

# ── Optional: Windows ANSI colour support ─────────────────────────────────────
if sys.platform == "win32":
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

import logger
import utils
from interface_monitor import InterfaceMonitor
from ping_monitor import PingMonitor
from traceroute import TracerouteMonitor

# ── ANSI colour helpers ────────────────────────────────────────────────────────
_USE_COLOR = sys.stdout.isatty() or sys.platform == "win32"


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def RED(t):    return _c(t, "91")
def YELLOW(t): return _c(t, "93")
def GREEN(t):  return _c(t, "92")
def CYAN(t):   return _c(t, "96")
def BOLD(t):   return _c(t, "1")
def DIM(t):    return _c(t, "2")


# ── Dashboard rendering ────────────────────────────────────────────────────────
_DASH_WIDTH = 90
_LATENCY_HISTORY_LEN = 30  # chars for sparkline


def _sparkline(values) -> str:
    """Render a small ASCII bar chart from latency values."""
    bars = " ▁▂▃▄▅▆▇█"
    if not values:
        return ""
    hi = max(values) or 1
    return "".join(bars[min(int(v / hi * 8), 8)] for v in list(values)[-_LATENCY_HISTORY_LEN:])


def _colour_latency(ms) -> str:
    if ms is None:
        return RED("TIMEOUT")
    s = f"{ms:6.1f} ms"
    if ms < 30:
        return GREEN(s)
    if ms < 100:
        return YELLOW(s)
    return RED(s)


def _colour_loss(pct: float) -> str:
    s = f"{pct:5.1f}%"
    if pct == 0:
        return GREEN(s)
    if pct < 5:
        return YELLOW(s)
    return RED(s)


def _colour_signal(dbm) -> str:
    if dbm is None:
        return DIM("N/A")
    s = f"{dbm} dBm"
    if dbm >= -60:
        return GREEN(s)
    if dbm >= -75:
        return YELLOW(s)
    return RED(s)


def render_dashboard(ping_mon: PingMonitor,
                     iface_mon: InterfaceMonitor,
                     gateway: str,
                     start_time: float,
                     traceroute_next: float):
    """Clear screen and draw the full dashboard."""
    # Move cursor to top-left (ANSI) rather than clearing — reduces flicker
    print("\033[H\033[J", end="")

    now = datetime.now().strftime("Date: %Y-%m-%d | Time: %H:%M:%S")
    elapsed = int(time.monotonic() - start_time)
    h, rem = divmod(elapsed, 3600)
    m, s = divmod(rem, 60)
    uptime = f"{h:02d}:{m:02d}:{s:02d}"

    sep = "─" * _DASH_WIDTH
    print(BOLD(CYAN(f"{'NetMon — Network Stability Monitor':^{_DASH_WIDTH}}")))
    print()
    print(DIM(f"{now} | Uptime: {uptime}"))
    print(sep)

    # ── Ping table ─────────────────────────────────────────────────────────────
    hdr = f"  {'TARGET':<18} {'LAST':>10} {'AVG':>10} {'MIN':>10} {'MAX':>10}   {'LOSS':>7}   {'JITTER':>8}"
    print(BOLD(hdr))
    print(sep)

    for target, st in ping_mon.stats.items():
        label = f"{'[GW] ' if target == gateway else '      '}{target}"
        last  = _colour_latency(st.last_latency)
        avg   = (_colour_latency(st.avg_latency))
        mn    = (_colour_latency(st.min_latency))
        mx    = (_colour_latency(st.max_latency))
        loss  = _colour_loss(st.packet_loss_pct)
        jit   = f"{st.jitter:6.1f} ms"
        print(f" {label:<18}    {last}   {avg}  {mn}  {mx}  {loss}  {jit}")

        spark = _sparkline(st.latencies)
        if spark:
            print(f"  {'':18} {DIM(spark)}")
    print(sep)

    # ── Interface panel ────────────────────────────────────────────────────────
    info = iface_mon.info
    conn_type = "WiFi" if info.is_wifi else "Ethernet"
    status_str = GREEN("UP") if info.is_up else RED("DOWN")
    print(f"  Interface: {BOLD(info.name)}  [{conn_type}]  IP: {info.ipv4}  Status: {status_str}")

    if info.is_wifi:
        sig = _colour_signal(info.signal_dbm)
        qual = info.signal_quality or "—"
        ssid = info.ssid or "—"
        ch = info.channel or "—"
        freq = info.frequency or "—"
        print(f"  SSID: {BOLD(ssid)}  Signal: {sig}  Quality: {qual}")
        print(f"  Channel: {ch}  Band/Radio: {freq}")
    else:
        spd = f"{info.speed_mbps} Mbps" if info.speed_mbps else "—"
        print(f"  Link speed: {BOLD(spd)}")

    sent_h = utils.bytes_human(info.bytes_sent)
    recv_h = utils.bytes_human(info.bytes_recv)
    print(f"  Sent: {sent_h}  Received: {recv_h}")
    print(sep)

    # ── Diagnostics summary ────────────────────────────────────────────────────
    gw_stats = ping_mon.stats.get(gateway)
    ext_targets = [t for t in ping_mon.stats if t != gateway]
    ext_stats = [ping_mon.stats[t] for t in ext_targets]

    diag_lines = []
    if gw_stats:
        if gw_stats.packet_loss_pct > 5:
            diag_lines.append(RED(f"⚠  Router unreachable / high loss ({gw_stats.packet_loss_pct:.1f}%) — check local connection"))
        elif gw_stats.last_latency and gw_stats.last_latency > 50:
            diag_lines.append(YELLOW(f"⚡  High gateway latency ({gw_stats.last_latency:.1f}ms) — router/modem issue?"))

        gw_ok = gw_stats.packet_loss_pct < 2 and (gw_stats.avg_latency or 0) < 50
        if gw_ok and ext_stats:
            ext_loss_avg = sum(e.packet_loss_pct for e in ext_stats) / len(ext_stats)
            if ext_loss_avg > 5:
                diag_lines.append(YELLOW("⚡  Gateway OK but external loss detected — ISP / upstream issue"))

    if not diag_lines:
        diag_lines.append(GREEN("✓  Connection looks healthy"))

    for line in diag_lines:
        print(f"  {line}")

    # Next traceroute countdown
    tr_in = max(0, int(traceroute_next - time.monotonic()))
    print(DIM(f"  Traceroute in {tr_in}s   |   Ctrl+C to stop and save log"))
    print(sep)


# ── Argument parsing ───────────────────────────────────────────────────────────
def _parse_args():
    p = argparse.ArgumentParser(description="NetMon — Network Stability Monitor")
    p.add_argument("--interval", type=float, default=1.0,
                   help="Ping interval in seconds (default: 1)")
    p.add_argument("--targets", nargs="+",
                   default=["8.8.8.8", "1.1.1.1"],
                   help="External ping targets")
    p.add_argument("--traceroute-interval", type=int, default=300,
                   help="Traceroute interval in seconds (default: 300)")
    p.add_argument("--latency-alert", type=float, default=150.0,
                   help="Latency alert threshold in ms (default: 150)")
    p.add_argument("--loss-alert", type=float, default=5.0,
                   help="Packet loss alert %% (default: 5)")
    p.add_argument("--config", type=str, default=None,
                   help="Path to JSON config file (overrides CLI args)")
    return p.parse_args()


def _load_config(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    args = _parse_args()
    cfg = {}
    if args.config:
        cfg = _load_config(args.config)

    interval        = cfg.get("interval", args.interval)
    ext_targets     = cfg.get("targets", args.targets)
    tr_interval     = cfg.get("traceroute_interval", args.traceroute_interval)
    latency_alert   = cfg.get("latency_alert_ms", args.latency_alert)
    loss_alert      = cfg.get("loss_alert_pct", args.loss_alert)

    gateway = utils.get_default_gateway()
    all_targets = [gateway] + [t for t in ext_targets if t != gateway]

    # ── Boot message ────────────────────────────────────────────────────────────
    print(BOLD(CYAN("  NetMon — Starting…")))
    print(f"  Gateway  : {gateway}")
    print(f"  Targets  : {', '.join(ext_targets)}")
    print(f"  Interval : {interval}s")
    print(f"  Logs dir : ./logs/")
    print()

    # ── Start subsystems ────────────────────────────────────────────────────────
    iface_mon = InterfaceMonitor()
    iface_mon.start()

    ping_mon = PingMonitor(all_targets, interval=interval)
    for t in all_targets:
        ping_mon.stats[t].alert_threshold_ms = latency_alert
        ping_mon.stats[t].loss_alert_threshold_pct = loss_alert

    tr_mon = TracerouteMonitor(all_targets, interval=tr_interval)

    logger.log_session_header(
        gateway=gateway,
        targets=all_targets,
        interface=iface_mon.info.name or "(detecting…)"
    )

    ping_mon.start()

    # Small delay to get first pings before traceroute blocks
    time.sleep(2)
    tr_mon.start()

    start_time = time.monotonic()
    tr_next = start_time + tr_interval

    # ── Graceful shutdown ───────────────────────────────────────────────────────
    _running = [True]

    def _shutdown(sig, frame):
        _running[0] = False

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    # ── Dashboard loop ──────────────────────────────────────────────────────────
    try:
        while _running[0]:
            render_dashboard(ping_mon, iface_mon, gateway, start_time, tr_next)

            if time.monotonic() >= tr_next:
                tr_next = time.monotonic() + tr_interval

            time.sleep(max(0.1, min(interval, 1.0)))
    finally:
        ping_mon.stop()
        tr_mon.stop()
        iface_mon.stop()

        # Build session summary
        summary = {}
        for target, st in ping_mon.stats.items():
            lbl = f"[GW] {target}" if target == gateway else target
            avg = f"{st.avg_latency:.1f}ms" if st.avg_latency else "N/A"
            summary[f"{lbl} — avg latency"] = avg
            summary[f"{lbl} — packet loss"] = f"{st.packet_loss_pct:.1f}%"
            summary[f"{lbl} — jitter"] = f"{st.jitter:.1f}ms"
            summary[f"{lbl} — sent/lost"] = f"{st.sent}/{st.lost}"

        logger.log_session_footer(summary)
        print()
        print(GREEN("  Session saved. Check ./logs/ for TXT and CSV files."))


if __name__ == "__main__":
    main()

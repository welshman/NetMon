# NetMon — Network Stability Monitor

A lightweight, real-time Python tool for diagnosing network issues between
your PC, router/modem, and the internet. Inspired by PingPlotter.

---

## Features

| Feature | Detail |
|---|---|
| Continuous ping | Gateway + external targets, 1-second default interval |
| Jitter tracking | Rolling 60-sample window |
| Packet loss detection | Alert at configurable threshold (default 5%) |
| Traceroute snapshots | Every 5 minutes, logs path changes |
| WiFi stats | SSID, RSSI, quality, channel (via `netsh` on Windows) |
| Ethernet stats | Link speed, up/down status |
| Live dashboard | ANSI colour-coded, sparkline graphs, diagnostic summary |
| TXT log | Human-readable, timestamped, full session |
| CSV log | Structured rows for spreadsheet analysis |
| Config file | JSON override for all settings |
| Diagnostic logic | Flags router issues vs ISP/external issues |

---

## Installation

### Requirements

- Python 3.10 or higher
- Windows 10/11 (primary), Linux, macOS

### Steps

```bash
# 1. Clone / copy the project folder
cd netmon

# 2. (Recommended) create a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Running

```bash
# Default (auto-detects gateway, pings 8.8.8.8 + 1.1.1.1)
python main.py

# Custom interval and targets
python main.py --interval 2 --targets 8.8.8.8 1.1.1.1 9.9.9.9

# With a config file
python main.py --config config.json

# Adjust alert thresholds
python main.py --latency-alert 100 --loss-alert 3
```

Press **Ctrl+C** to stop. Logs are saved to `./logs/`.

---

## Live Dashboard Example

```
                 NetMon — Network Stability Monitor
  2025-04-09 03:42:01   uptime 00:05:12
────────────────────────────────────────────────────────────────────────
  TARGET             LAST        AVG        MIN        MAX     LOSS  JITTER
────────────────────────────────────────────────────────────────────────
  [GW] 192.168.1.1     4.2 ms     3.9 ms     2.1 ms     8.3 ms   0.0%   0.8 ms
                    ▂▁▁▂▁▁▃▁▁▂▁
        8.8.8.8        12.1 ms    11.8 ms     9.4 ms    18.2 ms   0.0%   1.2 ms
                    ▂▂▁▂▁▃▁▁▂▂▁
        1.1.1.1        14.3 ms    13.5 ms    10.2 ms    19.7 ms   0.0%   1.4 ms
                    ▂▁▂▁▂▁▁▃▂▁▁
────────────────────────────────────────────────────────────────────────
  Interface: Wi-Fi  [WiFi]  IP: 192.168.1.42  Status: UP
  SSID: MyHomeWifi  Signal: -62 dBm  Quality: 74%
  Channel: 6  Band/Radio: 802.11n
  Sent: 1.2 MB  Received: 8.7 MB
────────────────────────────────────────────────────────────────────────
  ✓  Connection looks healthy
  Traceroute in 287s   |   Ctrl+C to stop and save log
────────────────────────────────────────────────────────────────────────
```

---

## Log File Example (TXT)

```
======================================================================
  NetMon — Network Stability Monitor
  Session started  : 2025-04-09 03:37:00
  Gateway          : 192.168.1.1
  External targets : 192.168.1.1, 8.8.8.8, 1.1.1.1
  Interface        : Wi-Fi
======================================================================
[2025-04-09 03:37:02] [INFO    ] --- Interface Stats ---
[2025-04-09 03:37:02] [INFO    ]   interface: Wi-Fi
[2025-04-09 03:37:02] [INFO    ]   type: WiFi
[2025-04-09 03:37:02] [INFO    ]   ip: 192.168.1.42
[2025-04-09 03:37:02] [INFO    ]   signal_dbm: -62
[2025-04-09 03:42:13] [ALERT   ] HIGH LATENCY: 8.8.8.8 185.3ms (threshold 150.0ms)
[2025-04-09 03:42:45] [ALERT   ] PACKET LOSS: 8.8.8.8 6.7% over last 60 samples
======================================================================
  SESSION SUMMARY
======================================================================
  [GW] 192.168.1.1 — avg latency    4.1ms
  [GW] 192.168.1.1 — packet loss    0.0%
  8.8.8.8 — avg latency             14.2ms
  8.8.8.8 — packet loss             1.7%
======================================================================
```

---

## Diagnostic Logic

| Symptom | Likely Cause |
|---|---|
| Gateway high latency / loss | Router/modem or local WiFi issue |
| Gateway OK, external loss | ISP or upstream problem |
| All targets timing out | Full disconnect or firewall blocking ICMP |
| Jitter spikes on WiFi | Wireless interference or signal degradation |
| Route change detected | ISP re-routing, VPN change |

---

## Module Map

```
netmon/
├── main.py              — Entry point, dashboard loop, CLI args
├── ping_monitor.py      — Threaded ICMP ping with stats
├── traceroute.py        — Periodic traceroute snapshots
├── interface_monitor.py — NIC / WiFi stats via psutil + netsh
├── logger.py            — TXT and CSV session logging
├── utils.py             — Gateway discovery, formatting helpers
├── config.json          — Optional JSON configuration
├── requirements.txt     — pip dependencies
└── logs/                — Generated per-session log files
```

---

## Tips

- Run in **Windows Terminal** or any terminal with ANSI support for full colour.
- On Windows, run as **Administrator** for more reliable `tracert` output.
- For 24/7 monitoring, wrap with `pythonw main.py` or create a Windows Task.
- Open the CSV log in Excel/Sheets for latency graphing.

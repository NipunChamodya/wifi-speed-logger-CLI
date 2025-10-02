#!/usr/bin/env python3
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

# Optional if you prefer importing the module rather than shelling out to speedtest-cli
try:
    import speedtest
except ImportError:
    print("speedtest module not found. Did you run: pip install -r requirements.txt ?", file=sys.stderr)
    sys.exit(1)

LOG_DIR = os.path.expanduser("~/WiFiSpeedLogger")
LOG_FILE = os.path.join(LOG_DIR, "logs.csv")

AIRPORT_CANDIDATES = [
    "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport",
    "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/A/Resources/airport",
    "airport",  # in case user symlinked it somewhere
]

CSV_HEADERS = [
    "timestamp_iso",
    "ssid",
    "bssid",
    "channel",
    "rssi_dbm",
    "noise_dbm",
    "snr_db",
    "tx_rate_mbps",
    "download_mbps",
    "upload_mbps",
    "ping_ms",
    "external_ip",
    "server_name",
    "server_country",
]

def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)

def find_airport():
    for p in AIRPORT_CANDIDATES:
        resolved = shutil.which(p) if os.path.sep not in p else (p if os.path.exists(p) else None)
        if resolved:
            return resolved
    return None

def parse_airport_output(text: str) -> dict:
    # airport -I outputs "key: value" lines. Example keys:
    #   SSID: MyWifi
    #   BSSID: a1:b2:c3:d4:e5:f6
    #   agrCtlRSSI: -56
    #   agrCtlNoise: -90
    #   channel: 36,80
    #   lastTxRate: 866
    #   state: running
    data = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()

    # Normalize/select fields
    ssid = data.get("SSID", "")
    bssid = data.get("BSSID", "")
    channel = data.get("channel", "")
    rssi = _to_int(data.get("agrCtlRSSI"))
    noise = _to_int(data.get("agrCtlNoise"))
    tx_rate = _to_float(data.get("lastTxRate"))

    snr = None
    if rssi is not None and noise is not None:
        snr = rssi - noise  # dB

    return {
        "ssid": ssid,
        "bssid": bssid,
        "channel": channel,
        "rssi_dbm": rssi,
        "noise_dbm": noise,
        "snr_db": snr,
        "tx_rate_mbps": tx_rate,
    }

def _to_int(val):
    try:
        return int(str(val).strip())
    except Exception:
        return None

def _to_float(val):
    try:
        return float(str(val).strip())
    except Exception:
        return None

def get_wifi_stats():
    airport = find_airport()
    if not airport:
        return {
            "ssid": "",
            "bssid": "",
            "channel": "",
            "rssi_dbm": None,
            "noise_dbm": None,
            "snr_db": None,
            "tx_rate_mbps": None,
        }
    try:
        out = subprocess.check_output([airport, "-I"], text=True)
        return parse_airport_output(out)
    except subprocess.CalledProcessError:
        return {
            "ssid": "",
            "bssid": "",
            "channel": "",
            "rssi_dbm": None,
            "noise_dbm": None,
            "snr_db": None,
            "tx_rate_mbps": None,
        }

def run_speedtest():
    # Using the Python library directly (more reliable than shelling out)
    s = speedtest.Speedtest()
    s.get_servers([])
    best = s.get_best_server()
    down = s.download()  # bits per second
    up = s.upload(pre_allocate=False)  # bits per second
    res = s.results.dict()
    # Convert to Mbps
    down_mbps = round(down / 1_000_000, 3)
    up_mbps = round(up / 1_000_000, 3)
    ping_ms = round(res.get("ping", best.get("latency", 0.0)), 2)

    server_name = f"{best.get('sponsor','')} - {best.get('name','')}".strip(" -")
    server_country = best.get("country", "")
    external_ip = res.get("client", {}).get("ip", "")

    return {
        "download_mbps": down_mbps,
        "upload_mbps": up_mbps,
        "ping_ms": ping_ms,
        "external_ip": external_ip,
        "server_name": server_name,
        "server_country": server_country,
    }

def append_csv(row: dict):
    file_exists = os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def main():
    ensure_dirs()

    timestamp_iso = dt.datetime.now().astimezone().isoformat(timespec="seconds")

    wifi = get_wifi_stats()
    speed = {}
    try:
        speed = run_speedtest()
    except Exception as e:
        # If speedtest fails, still log Wi-Fi with blanks
        speed = {
            "download_mbps": None,
            "upload_mbps": None,
            "ping_ms": None,
            "external_ip": "",
            "server_name": "",
            "server_country": "",
        }

    row = {
        "timestamp_iso": timestamp_iso,
        **wifi,
        **speed,
    }

    append_csv(row)

if __name__ == "__main__":
    main()

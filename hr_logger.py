#!/usr/bin/env python3
"""
HR logger -- INDEPENDENT of BioNode.

Captures live HR + RR intervals from a BLE Heart Rate strap (Garmin HRM-Pro Plus)
and writes to its OWN SQLite DB. Does NOT touch BioNode's I2C bus, DB, or ports.
The Garmin watch keeps recording natively over ANT+ in parallel -- that is the
PRIMARY log. This script is the enhancement / live-broadcast prototype. If it
fails, you lose nothing: the watch already has the data.

Requires: pip3 install bleak
"""
import asyncio
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path

from bleak import BleakScanner, BleakClient

# ---- config ----
STRAP_NAME_MATCH = "HRMPro+:aris"       # substring match on advertised name; adjust to your strap
STRAP_ADDRESS = "D3:83:17:BB:BA:C6"     # optional: hardcode MAC to skip scan, e.g. "C1:23:45:67:89:AB"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"  # 0x2A37
DB_PATH = Path(__file__).parent / "data" / "hr_mission.db"
RECONNECT_DELAY = 5             # seconds between reconnect attempts
SCAN_TIMEOUT = 15              # seconds per scan


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS hr (
            ts_utc   TEXT NOT NULL,
            hr_bpm   INTEGER,
            rr_ms    TEXT,       -- comma-separated RR intervals in ms (may be empty)
            contact  INTEGER     -- 1=good contact, 0=poor, NULL=unsupported
        );
        """
    )
    con.commit()
    return con


def parse_hr_measurement(data: bytearray):
    """Parse BLE Heart Rate Measurement characteristic (0x2A37)."""
    flags = data[0]
    hr_16bit          = flags & 0x01
    contact_detected  = (flags >> 1) & 0x01
    contact_supported = (flags >> 2) & 0x01
    energy_present    = (flags >> 3) & 0x01
    rr_present        = (flags >> 4) & 0x01

    idx = 1
    if hr_16bit:
        hr = struct.unpack_from("<H", data, idx)[0]
        idx += 2
    else:
        hr = data[idx]
        idx += 1

    if energy_present:
        idx += 2  # skip energy expended (uint16)

    rr_list = []
    if rr_present:
        while idx + 2 <= len(data):
            rr_raw = struct.unpack_from("<H", data, idx)[0]
            idx += 2
            rr_list.append(round(rr_raw * 1000.0 / 1024.0, 1))  # 1/1024 s -> ms

    contact = (1 if contact_detected else 0) if contact_supported else None
    return hr, rr_list, contact


async def run():
    con = init_db()

    def handler(_char, data):
        hr, rr_list, contact = parse_hr_measurement(bytearray(data))
        ts = datetime.now(timezone.utc).isoformat()
        con.execute(
            "INSERT INTO hr (ts_utc, hr_bpm, rr_ms, contact) VALUES (?,?,?,?)",
            (ts, hr, ",".join(str(x) for x in rr_list), contact),
        )
        con.commit()
        print(f"{ts}  HR={hr:3d} bpm  RR={rr_list}  contact={contact}")

    while True:  # outer reconnect loop -- straps drop, survive it
        try:
            address = STRAP_ADDRESS
            if address is None:
                print("Scanning for strap...")
                devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
                for d in devices:
                    print(f"  found: {d.name}  [{d.address}]")
                    if d.name and STRAP_NAME_MATCH.lower() in d.name.lower():
                        address = d.address
                        break
                if address is None:
                    print(
                        f"No device matching '{STRAP_NAME_MATCH}'. "
                        f"Wear the strap (wet the contacts) and retry, "
                        f"or hardcode STRAP_ADDRESS from the list above."
                    )
                    await asyncio.sleep(RECONNECT_DELAY)
                    continue

            print(f"Connecting to {address} ...")
            async with BleakClient(address) as client:
                print("Connected. Subscribing to HR...")
                await client.start_notify(HR_MEASUREMENT_UUID, handler)
                while client.is_connected:
                    await asyncio.sleep(1)
                print("Disconnected.")
        except Exception as e:
            print(f"BLE error: {e}. Reconnecting in {RECONNECT_DELAY}s...")
        await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nStopped.")

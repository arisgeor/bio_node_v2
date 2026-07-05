#!/usr/bin/env python3
"""
BioNode V2.1 — headless logging loop
====================================

Reads all sensors and writes one row per sample into data/bionode.db.
Designed for unattended multi-day soak testing before the AAT-112 analog mission.

Sensor roles (do NOT blur — see schema.sql):
  SCD30    -> co2_ppm + scd30_temp_c / scd30_rh_pct   (PRIMARY CO2 & T/RH)
  BME280   -> bme280_*                                 (pressure + T/RH CROSS-CHECK)
  SGP30    -> tvoc_ppb (real) + eco2_proxy_ppm (PROXY, never a real CO2 value)
  BH1750   -> lux                                      (software bus 3)
  MAX30102 -> heart_rate_bpm / spo2_pct
  MLX90614 -> surface_temp_c (object) + mlx_ambient_c

Design rules:
  * Fail-soft: any sensor that errors logs NULL for its columns; the loop continues.
    A single sensor hiccup must never kill a multi-day run.
  * UTC storage, ISO-8601. Display/convert to local elsewhere.
  * WAL is enabled on the DB file already; a reboot mid-run costs seconds, not the set.
  * Inserts a 'power_restart' event on startup so swap/reboot gaps are visible.

Run manually:
    source ~/bio_node_v2/.venv/bin/activate
    python3 logger.py

Run headless under systemd (the real soak-test mode) — see bionode-logger.service.
Stop with Ctrl+C when running manually; it closes the session cleanly.
"""

from __future__ import annotations

import datetime
import signal
import sqlite3
import sys
import time
from typing import Optional

# -----------------------------
# CONFIG
# -----------------------------
DB_PATH = "/home/aris/bio_node_v2/data/bionode.db"

MISSION_NAME = "AAT-112-soak"          # soak test uses its own mission row
NODE_ID = "bionode-01"
SITE = "Athens (soak test)"
ALTITUDE_M = 70.0

SUBJECT_ID = "aris"
SAMPLE_INTERVAL_S = 2                    # constant 2s for the soak test

# SCD30 mission config (must match the validated test)
SCD30_ALTITUDE_M = 70
SCD30_ASC_OFF = True

# -----------------------------
# SENSOR SETUP
# -----------------------------
sys.path.insert(0, "/home/aris/bio_node_v2")

import board
import busio
import adafruit_sgp30
import adafruit_mlx90614
from adafruit_bme280 import basic as adafruit_bme280
import adafruit_bh1750
from adafruit_extended_bus import ExtendedI2C
import adafruit_scd30
from DFRobot_BloodOxygen_S import DFRobot_BloodOxygen_S_i2c


def ts_utc() -> str:
    """UTC timestamp, ISO-8601, second resolution."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --- Primary I2C bus (bus 1) ---
_i2c = busio.I2C(board.SCL, board.SDA)

# SCD30 (primary CO2)
try:
    _scd30 = adafruit_scd30.SCD30(_i2c)
    _scd30.self_calibration_enabled = not SCD30_ASC_OFF
    _scd30.altitude = SCD30_ALTITUDE_M
    _scd30.measurement_interval = SAMPLE_INTERVAL_S
    SCD30_OK = True
    print(f"SCD30 initialized (ASC={_scd30.self_calibration_enabled}, alt={_scd30.altitude}m).")
except Exception as e:
    _scd30 = None
    SCD30_OK = False
    print(f"SCD30 init failed: {e}")

# SGP30 (TVOC real, eCO2 proxy)
try:
    _sgp30 = adafruit_sgp30.Adafruit_SGP30(_i2c)
    _sgp30.iaq_init()
    SGP30_OK = True
    print("SGP30 initialized.")
except Exception as e:
    _sgp30 = None
    SGP30_OK = False
    print(f"SGP30 init failed: {e}")

# MLX90614 (surface temp)
try:
    _mlx = adafruit_mlx90614.MLX90614(_i2c)
    MLX_OK = True
    print("MLX90614 initialized.")
except Exception as e:
    _mlx = None
    MLX_OK = False
    print(f"MLX90614 init failed: {e}")

# BME280 (cross-check T/RH/pressure)
try:
    _bme280 = adafruit_bme280.Adafruit_BME280_I2C(_i2c, address=0x77)
    BME280_OK = True
    print("BME280 initialized.")
except Exception as e:
    _bme280 = None
    BME280_OK = False
    print(f"BME280 init failed: {e}")

# MAX30102 (HR/SpO2)
try:
    _max30102 = DFRobot_BloodOxygen_S_i2c(bus=1, addr=0x57)
    if _max30102.begin():
        _max30102.sensor_start_collect()
        MAX_OK = True
        print("MAX30102 initialized.")
    else:
        MAX_OK = False
        print("MAX30102 begin() failed.")
except Exception as e:
    _max30102 = None
    MAX_OK = False
    print(f"MAX30102 init failed: {e}")

# --- Software I2C bus (bus 3): BH1750 only ---
try:
    _i2c3 = ExtendedI2C(3)
    _bh1750 = adafruit_bh1750.BH1750(_i2c3, address=0x23)
    BH1750_OK = True
    print("BH1750 initialized on bus 3.")
except Exception as e:
    _bh1750 = None
    BH1750_OK = False
    print(f"BH1750 init failed: {e}")


# -----------------------------
# SENSOR READ HELPERS (all fail-soft -> None)
# -----------------------------
def read_scd30() -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Returns (co2_ppm, temp_c, rh_pct). Only reads when a fresh sample is ready."""
    if not SCD30_OK:
        return None, None, None
    try:
        if _scd30.data_available:
            return (
                round(float(_scd30.CO2), 1),
                round(float(_scd30.temperature), 2),
                round(float(_scd30.relative_humidity), 2),
            )
        return None, None, None
    except Exception as e:
        print(f"SCD30 read error: {e}")
        return None, None, None


def read_sgp30() -> tuple[Optional[int], Optional[int]]:
    """Returns (tvoc_ppb, eco2_proxy_ppm)."""
    if not SGP30_OK:
        return None, None
    try:
        eco2, tvoc = _sgp30.iaq_measure()
        return int(tvoc), int(eco2)
    except Exception as e:
        print(f"SGP30 read error: {e}")
        return None, None


def read_mlx() -> tuple[Optional[float], Optional[float]]:
    """Returns (surface_temp_c, ambient_c)."""
    if not MLX_OK:
        return None, None
    try:
        return (
            round(float(_mlx.object_temperature), 1),
            round(float(_mlx.ambient_temperature), 1),
        )
    except Exception as e:
        print(f"MLX90614 read error: {e}")
        return None, None


def read_bme280() -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Returns (temp_c, rh_pct, pressure_hpa)."""
    if not BME280_OK:
        return None, None, None
    try:
        return (
            round(float(_bme280.temperature), 1),
            round(float(_bme280.relative_humidity), 1),
            round(float(_bme280.pressure), 1),
        )
    except Exception as e:
        print(f"BME280 read error: {e}")
        return None, None, None


def read_max30102() -> tuple[Optional[int], Optional[int]]:
    """Returns (heart_rate_bpm, spo2_pct). Sanity-filtered against ghost readings."""
    if not MAX_OK:
        return None, None
    try:
        _max30102.get_heartbeat_SPO2()
        hr = _max30102.heartbeat
        spo2 = _max30102.SPO2
        hr_val = None if (hr in (-1, 0) or hr > 200) else int(hr)
        spo2_val = None if (spo2 in (-1, 0) or spo2 < 70) else int(spo2)
        return hr_val, spo2_val
    except Exception as e:
        print(f"MAX30102 read error: {e}")
        return None, None


def read_bh1750() -> Optional[float]:
    if not BH1750_OK:
        return None
    try:
        return round(float(_bh1750.lux), 1)
    except Exception as e:
        print(f"BH1750 read error: {e}")
        return None


# -----------------------------
# DATABASE
# -----------------------------
def get_or_create_mission(conn: sqlite3.Connection) -> int:
    """One mission row for the soak test; reuse it across restarts."""
    row = conn.execute(
        "SELECT mission_id FROM missions WHERE name = ? AND node_id = ?",
        (MISSION_NAME, NODE_ID),
    ).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO missions (name, node_id, site, altitude_m, start_utc) "
        "VALUES (?, ?, ?, ?, ?)",
        (MISSION_NAME, NODE_ID, SITE, ALTITUDE_M, ts_utc()),
    )
    conn.commit()
    return cur.lastrowid


def create_session(conn: sqlite3.Connection, mission_id: int) -> int:
    """Open a new session on every startup (each restart = a new session)."""
    cur = conn.execute(
        "INSERT INTO sessions (mission_id, subject_id, start_utc, sample_interval_seconds) "
        "VALUES (?, ?, ?, ?)",
        (mission_id, SUBJECT_ID, ts_utc(), SAMPLE_INTERVAL_S),
    )
    conn.commit()
    return cur.lastrowid


def insert_power_restart_event(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute(
        "INSERT INTO events (session_id, timestamp_utc, event_type, label) "
        "VALUES (?, ?, 'power_restart', 'logger start')",
        (session_id, ts_utc()),
    )
    conn.commit()


def mission_day(conn: sqlite3.Connection, mission_id: int) -> int:
    """Whole days since mission start_utc."""
    row = conn.execute(
        "SELECT start_utc FROM missions WHERE mission_id = ?", (mission_id,)
    ).fetchone()
    if not row:
        return 0
    start = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=datetime.timezone.utc
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - start).days


# -----------------------------
# MAIN LOOP
# -----------------------------
_running = True


def _handle_stop(signum, frame):
    global _running
    _running = False


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    mission_id = get_or_create_mission(conn)
    session_id = create_session(conn, mission_id)
    insert_power_restart_event(conn, session_id)

    print(f"\nMission {mission_id}, session {session_id}. Logging every "
          f"{SAMPLE_INTERVAL_S}s. Ctrl+C to stop.\n")

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    written = 0
    while _running:
        loop_start = time.monotonic()

        co2, scd_t, scd_rh = read_scd30()
        tvoc, eco2_proxy = read_sgp30()
        surf_t, mlx_amb = read_mlx()
        bme_t, bme_rh, bme_p = read_bme280()
        hr, spo2 = read_max30102()
        lux = read_bh1750()

        conn.execute(
            """
            INSERT INTO readings (
                session_id, timestamp_utc, mission_day, activity_context, location_tag,
                co2_ppm, scd30_temp_c, scd30_rh_pct,
                bme280_temp_c, bme280_rh_pct, bme280_pressure_hpa,
                tvoc_ppb, eco2_proxy_ppm,
                lux,
                heart_rate_bpm, spo2_pct,
                surface_temp_c, mlx_ambient_c
            ) VALUES (?, ?, ?, 'unspecified', NULL,
                      ?, ?, ?,
                      ?, ?, ?,
                      ?, ?,
                      ?,
                      ?, ?,
                      ?, ?)
            """,
            (
                session_id, ts_utc(), mission_day(conn, mission_id),
                co2, scd_t, scd_rh,
                bme_t, bme_rh, bme_p,
                tvoc, eco2_proxy,
                lux,
                hr, spo2,
                surf_t, mlx_amb,
            ),
        )
        conn.commit()
        written += 1

        if written % 30 == 0:
            print(f"[{ts_utc()}] {written} rows | CO2={co2} HR={hr} SpO2={spo2} "
                  f"surf={surf_t} lux={lux}")

        elapsed = time.monotonic() - loop_start
        time.sleep(max(0.0, SAMPLE_INTERVAL_S - elapsed))

    # Clean shutdown: close the session
    conn.execute(
        "UPDATE sessions SET end_utc = ? WHERE session_id = ?",
        (ts_utc(), session_id),
    )
    conn.commit()
    conn.close()
    print(f"\nStopped. {written} rows written. Session {session_id} closed.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import random
import time
from dataclasses import dataclass, asdict
from typing import Optional

from flask import Flask, jsonify, render_template

#SPG30 imports
import board
import busio
import adafruit_sgp30

#MLX60614 imports
import adafruit_mlx90614

#MAX30102 imports
import sys
sys.path.insert(0, '/home/aris/bio_node_v2')
from DFRobot_BloodOxygen_S import DFRobot_BloodOxygen_S_i2c


app = Flask(__name__)

# -----------------------------
# CONFIG
# -----------------------------

# SGP30 setup
try:
    _i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
    _sgp30 = adafruit_sgp30.Adafruit_SGP30(_i2c)
    _sgp30.iaq_init()
    SGP30_AVAILABLE = True
    print("SGP30 initialized.")
except Exception as e:
    _sgp30 = None
    SGP30_AVAILABLE = False
    print(f"SGP30 init failed: {e}")

# -------------------------------------------------------    

# MLX90614 setup
try:
    _mlx = adafruit_mlx90614.MLX90614(_i2c)
    MLX_AVAILABLE = True
    print("MLX90614 initialized.")
except Exception as e:
    _mlx = None
    MLX_AVAILABLE = False
    print(f"MLX90614 init failed: {e}")

# -------------------------------------------------------    

# MAX30102 (DFRobot Gravity) setup
try:
    _max30102 = DFRobot_BloodOxygen_S_i2c(bus=1, addr=0x57)
    if _max30102.begin():
        _max30102.sensor_start_collect()
        MAX30102_AVAILABLE = True
        print("MAX30102 initialized.")
    else:
        MAX30102_AVAILABLE = False
        print("MAX30102 begin() failed.")
except Exception as e:
    _max30102 = None
    MAX30102_AVAILABLE = False
    print(f"MAX30102 init failed: {e}")

# -------------------------------------------------------    


# Thresholds for rough demo logic
TEMP_HIGH_C = 35.5
HR_HIGH_BPM = 110
SPO2_LOW = 94
TVOC_HIGH_PP_B = 400  # optional if you add SGP30 later


# -----------------------------
# DATA MODEL
# -----------------------------
@dataclass
class Vitals:
    timestamp: float
    heart_rate_bpm: Optional[int]
    spo2_percent: Optional[int]
    body_temp_c: Optional[float]
    tvoc_ppb: Optional[int]
    eco2_ppm: Optional[int]
    alert_level: str
    alerts: list[str]


# -----------------------------
# MOCK SENSOR READERS
# Usuful when testing without hardware
# -----------------------------
def read_mock_heart_rate() -> Optional[int]:
    return random.randint(68, 92)

def read_mock_spo2() -> Optional[int]:
    return random.randint(95, 99)

def read_mock_temperature() -> Optional[float]:
    return round(random.uniform(36.2, 37.4), 1)

def read_mock_tvoc() -> Optional[int]:
    return random.randint(40, 180)

def read_mock_eco2() -> Optional[int]:
    return random.randint(450, 900)


# -----------------------------
# REAL SENSOR READERS
# Replace these later
# -----------------------------
def read_real_heart_rate() -> Optional[int]:
    if not MAX30102_AVAILABLE:
        return None
    try:
        _max30102.get_heartbeat_SPO2()
        hr = _max30102.heartbeat
        if hr == -1:
            return None
        return int(hr)
    except Exception as e:
        print(f"MAX30102 HR read error: {e}")
        return None


def read_real_spo2() -> Optional[int]:
    if not MAX30102_AVAILABLE:
        return None
    try:
        _max30102.get_heartbeat_SPO2()
        spo2 = _max30102.SPO2
        if spo2 == -1:
            return None
        return int(spo2)
    except Exception as e:
        print(f"MAX30102 SpO2 read error: {e}")
        return None


def read_real_temperature() -> Optional[float]:
    if not MLX_AVAILABLE:
        return None
    try:
        return round(float(_mlx.object_temperature), 1)
    except Exception as e:
        print(f"MLX90614 read error: {e}")
        return None


def read_real_eco2() -> Optional[int]:
    if not SGP30_AVAILABLE:
        return None
    try:
        eco2, tvoc = _sgp30.iaq_measure()
        return int(eco2)
    except Exception as e:
        print(f"SGP30 eCO2 read error: {e}")
        return None
    

def read_real_tvoc() -> Optional[int]:
    if not SGP30_AVAILABLE:
        return None
    try:
        eco2, tvoc = _sgp30.iaq_measure()
        return int(tvoc)
    except Exception as e:
        print(f"SGP30 TVOC read error: {e}")
        return None

# -----------------------------
# UNIFIED SENSOR ACCESS
# -----------------------------

MOCK_SGP30 = False     # real sensor live
MOCK_MLX = False        # real sensor live
MOCK_PHYSIO = False     # real sensor live

def get_heart_rate() -> Optional[int]:
    return read_mock_heart_rate() if MOCK_PHYSIO else read_real_heart_rate()

def get_spo2() -> Optional[int]:
    return read_mock_spo2() if MOCK_PHYSIO else read_real_spo2()

def get_temperature() -> Optional[float]:
    return read_mock_temperature() if MOCK_MLX else read_real_temperature()

def get_tvoc() -> Optional[int]:
    return read_mock_tvoc() if MOCK_SGP30 else read_real_tvoc()

def get_eco2() -> Optional[int]:
    return read_mock_eco2() if MOCK_SGP30 else read_real_eco2()

# -----------------------------
# ALERT LOGIC
# -----------------------------
def evaluate_alerts(
    heart_rate_bpm: Optional[int],
    spo2_percent: Optional[int],
    body_temp_c: Optional[float],
    tvoc_ppb: Optional[int],
    eco2_ppm: Optional[int],
) -> tuple[str, list[str]]:
    alerts: list[str] = []

    if body_temp_c is not None and body_temp_c >= TEMP_HIGH_C:
        alerts.append(f"High temperature: {body_temp_c:.1f} °C")

    if heart_rate_bpm is not None and heart_rate_bpm >= HR_HIGH_BPM:
        alerts.append(f"High heart rate: {heart_rate_bpm} bpm")

    if spo2_percent is not None and spo2_percent <= SPO2_LOW:
        alerts.append(f"Low SpO2: {spo2_percent}%")

    if tvoc_ppb is not None and tvoc_ppb >= 400:
        alerts.append(f"High TVOC: {tvoc_ppb} ppb")

    if eco2_ppm is not None and eco2_ppm >= 1200:
        alerts.append(f"High eCO2: {eco2_ppm} ppm")

    # crude combined rule
    if (
        heart_rate_bpm is not None
        and spo2_percent is not None
        and heart_rate_bpm >= 105
        and spo2_percent <= 94
    ):
        alerts.append("Combined physiological strain pattern detected")

    if not alerts:
        return "normal", []

    if len(alerts) == 1:
        return "warning", alerts

    return "critical", alerts


def collect_vitals() -> Vitals:
    heart_rate_bpm = get_heart_rate()
    spo2_percent = get_spo2()
    body_temp_c = get_temperature()
    tvoc_ppb = get_tvoc()
    eco2_ppm = get_eco2()

    alert_level, alerts = evaluate_alerts(
        heart_rate_bpm=heart_rate_bpm,
        spo2_percent=spo2_percent,
        body_temp_c=body_temp_c,
        tvoc_ppb=tvoc_ppb,
        eco2_ppm=eco2_ppm,
    )

    return Vitals(
        timestamp=time.time(),
        heart_rate_bpm=heart_rate_bpm,
        spo2_percent=spo2_percent,
        body_temp_c=body_temp_c,
        tvoc_ppb=tvoc_ppb,
        eco2_ppm=eco2_ppm,
        alert_level=alert_level,
        alerts=alerts,
    )


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/vitals")
def api_vitals():
    vitals = collect_vitals()
    data = asdict(vitals)
    data['mock'] = {
        'heart_rate': MOCK_PHYSIO,
        'spo2': MOCK_PHYSIO,
        'temperature': MOCK_MLX,
        'tvoc': MOCK_SGP30,
        'eco2': MOCK_SGP30,
    }
    return jsonify(data)


if __name__ == "__main__":
    # host=0.0.0.0 makes it visible from browser on your network
    app.run(host="0.0.0.0", port=5000, debug=True)

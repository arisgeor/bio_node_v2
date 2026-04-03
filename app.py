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

#BME280 imports
from adafruit_bme280 import basic as adafruit_bme280

#BH1750 imports
import adafruit_bh1750
from adafruit_extended_bus import ExtendedI2C


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

# BME280 setup
try:
    _bme280 = adafruit_bme280.Adafruit_BME280_I2C(_i2c, address=0x77)
    BME280_AVAILABLE = True
    print("BME280 initialized.")
except Exception as e:
    _bme280 = None
    BME280_AVAILABLE = False
    print(f"BME280 init failed: {e}")

# -------------------------------------------------------    

# BH1750 setup (on I2C bus 3 — separate bus to avoid SGP30 conflict)
try:
    _i2c3 = ExtendedI2C(3)
    _bh1750 = adafruit_bh1750.BH1750(_i2c3, address=0x23)
    BH1750_AVAILABLE = True
    print("BH1750 initialized on bus 3.")
except Exception as e:
    _bh1750 = None
    BH1750_AVAILABLE = False
    print(f"BH1750 init failed: {e}")

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
    ambient_temp_c: Optional[float]
    humidity_percent: Optional[float]
    pressure_hpa: Optional[float]
    light_lux: Optional[float]
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

def read_mock_ambient_temp() -> Optional[float]:
    return round(random.uniform(20.0, 25.0), 1)

def read_mock_humidity() -> Optional[float]:
    return round(random.uniform(35.0, 55.0), 1)

def read_mock_pressure() -> Optional[float]:
    return round(random.uniform(985.0, 1015.0), 1)

def read_mock_light() -> Optional[float]:
    return round(random.uniform(100.0, 500.0), 1)

# -----------------------------
# REAL SENSOR READERS
# -----------------------------

#MAX30102
def read_real_heart_rate() -> Optional[int]:
    if not MAX30102_AVAILABLE:
        return None
    try:
        _max30102.get_heartbeat_SPO2()
        hr = _max30102.heartbeat
        if hr == -1 or hr == 0 or hr > 200:
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
        if spo2 == -1 or spo2 == 0 or spo2 < 70:
            return None
        return int(spo2)
    except Exception as e:
        print(f"MAX30102 SpO2 read error: {e}")
        return None

#MLX90614
def read_real_temperature() -> Optional[float]:
    if not MLX_AVAILABLE:
        return None
    try:
        return round(float(_mlx.object_temperature), 1)
    except Exception as e:
        print(f"MLX90614 read error: {e}")
        return None
    
#SPG30 
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

#ΒΜΕ280
def read_real_ambient_temp() -> Optional[float]:
    if not BME280_AVAILABLE:
        return None
    try:
        return round(float(_bme280.temperature), 1)
    except Exception as e:
        print(f"BME280 temp read error: {e}")
        return None

def read_real_humidity() -> Optional[float]:
    if not BME280_AVAILABLE:
        return None
    try:
        return round(float(_bme280.relative_humidity), 1)
    except Exception as e:
        print(f"BME280 humidity read error: {e}")
        return None

def read_real_pressure() -> Optional[float]:
    if not BME280_AVAILABLE:
        return None
    try:
        return round(float(_bme280.pressure), 1)
    except Exception as e:
        print(f"BME280 pressure read error: {e}")
        return None


#ΒH1750
def read_real_light() -> Optional[float]:
    if not BH1750_AVAILABLE:
        return None
    try:
        return round(float(_bh1750.lux), 1)
    except Exception as e:
        print(f"BH1750 read error: {e}")
        return None

# -----------------------------
# UNIFIED SENSOR ACCESS
# -----------------------------

MOCK_SGP30 = False     # real sensor live
MOCK_MLX = False        # real sensor live
MOCK_PHYSIO = False     # real sensor live
MOCK_BME280 = False    # real sensor live
MOCK_BH1750 = False    # real sensor live

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

def get_ambient_temp() -> Optional[float]:
    return read_mock_ambient_temp() if MOCK_BME280 else read_real_ambient_temp()

def get_humidity() -> Optional[float]:
    return read_mock_humidity() if MOCK_BME280 else read_real_humidity()

def get_pressure() -> Optional[float]:
    return read_mock_pressure() if MOCK_BME280 else read_real_pressure()

def get_light() -> Optional[float]:
    return read_mock_light() if MOCK_BH1750 else read_real_light()

# -----------------------------
# ALERT LOGIC
# -----------------------------
def evaluate_alerts(
    heart_rate_bpm: Optional[int],
    spo2_percent: Optional[int],
    body_temp_c: Optional[float],
    tvoc_ppb: Optional[int],
    eco2_ppm: Optional[int],
    light_lux: Optional[float]
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
    ambient_temp_c = get_ambient_temp()
    humidity_percent = get_humidity()
    pressure_hpa = get_pressure()
    light_lux = get_light()

    alert_level, alerts = evaluate_alerts(
        heart_rate_bpm=heart_rate_bpm,
        spo2_percent=spo2_percent,
        body_temp_c=body_temp_c,
        tvoc_ppb=tvoc_ppb,
        eco2_ppm=eco2_ppm,
        light_lux=light_lux,
    )

    return Vitals(
        timestamp=time.time(),
        heart_rate_bpm=heart_rate_bpm,
        spo2_percent=spo2_percent,
        body_temp_c=body_temp_c,
        tvoc_ppb=tvoc_ppb,
        eco2_ppm=eco2_ppm,
        ambient_temp_c=ambient_temp_c,
        humidity_percent=humidity_percent,
        pressure_hpa=pressure_hpa,
        light_lux=light_lux,
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
    'ambient_temp': MOCK_BME280,
    'humidity': MOCK_BME280,
    'pressure': MOCK_BME280,
    'light': MOCK_BH1750,
}
    return jsonify(data)


if __name__ == "__main__":
    # host=0.0.0.0 makes it visible from browser on your network
    app.run(host="0.0.0.0", port=5000, debug=True)

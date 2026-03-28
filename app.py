from __future__ import annotations

import random
import time
from dataclasses import dataclass, asdict
from typing import Optional

from flask import Flask, jsonify, render_template

app = Flask(__name__)

# -----------------------------
# CONFIG
# -----------------------------
USE_MOCK_DATA = True

# Thresholds for rough demo logic
TEMP_HIGH_C = 37.8
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
    """
    Replace this with your MAX30102/MAX30105 logic.
    Return an integer BPM or None if read fails.
    """
    return None


def read_real_spo2() -> Optional[int]:
    """
    Replace this with your MAX30102/MAX30105 logic.
    Return integer SpO2 or None if read fails.
    """
    return None


def read_real_temperature() -> Optional[float]:
    """
    Replace this with your MLX90614 logic.
    Return float temperature in C or None if read fails.
    """
    return None


def read_real_tvoc() -> Optional[int]:
    """
    Replace this later with SGP30 logic if/when ready.
    """
    return None


def read_real_eco2() -> Optional[int]:
    """
    Replace this later with SGP30 logic if/when ready.
    """
    return None


# -----------------------------
# UNIFIED SENSOR ACCESS
# -----------------------------
def get_heart_rate() -> Optional[int]:
    return read_mock_heart_rate() if USE_MOCK_DATA else read_real_heart_rate()


def get_spo2() -> Optional[int]:
    return read_mock_spo2() if USE_MOCK_DATA else read_real_spo2()


def get_temperature() -> Optional[float]:
    return read_mock_temperature() if USE_MOCK_DATA else read_real_temperature()


def get_tvoc() -> Optional[int]:
    return read_mock_tvoc() if USE_MOCK_DATA else read_real_tvoc()


def get_eco2() -> Optional[int]:
    return read_mock_eco2() if USE_MOCK_DATA else read_real_eco2()


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
    return jsonify(asdict(vitals))


if __name__ == "__main__":
    # host=0.0.0.0 makes it visible from browser on your network
    app.run(host="0.0.0.0", port=5000, debug=True)

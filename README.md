# BioNode V2

A multi-sensor physiological and environmental monitoring node built on Raspberry Pi 4. BioNode V2 combines real-time physiological sensing (heart rate, SpO2, skin surface temperature) with environmental monitoring (air quality, atmospheric conditions, ambient light) to detect environmental degradation and its potential physiological impact on occupants of enclosed spaces.

## What it does

BioNode V2 reads five I2C sensors at 2-second intervals and serves a live dashboard over the local network via Flask. Each reading is evaluated against sourced clinical and occupational thresholds, producing a three-tier system state: **Normal**, **Caution**, or **Critical**. The system is designed for trend monitoring and threshold-based early warning — not clinical diagnosis.

The core thesis: correlating environmental degradation (rising CO2, declining air quality, temperature extremes) with physiological response (elevated heart rate, declining SpO2) in enclosed or isolated environments.

## Sensors

| Sensor | Measurement | I2C Address | Bus |
|--------|------------|-------------|-----|
| MAX30102 (DFRobot Gravity SEN0518) | Heart rate, SpO2 | 0x57 | 1 |
| MLX90614 | Skin surface temperature (non-contact IR) | 0x5A | 1 |
| SGP30 | Estimated CO2 (eCO2), Total VOC (TVOC) | 0x58 | 1 |
| BME280 | Ambient temperature, relative humidity, barometric pressure | 0x77 | 1 |
| BH1750 | Ambient light intensity | 0x23 | 3 |

The BH1750 runs on a dedicated software I2C bus (GPIO 17/27) to avoid signal interference with the SGP30's CRC-checked protocol on the primary bus.

### Sensor notes

**MAX30102 (DFRobot Gravity SEN0518):** This is not a bare MAX30102 breakout. The DFRobot module includes an onboard V8520 MCU that runs a PPG algorithm and outputs processed heart rate and SpO2 values directly over I2C. The host system does not perform signal processing — it reads computed values from the MCU. Heart rate updates every ~4 seconds. Readings are sensitive to finger placement and pressure. Values during the first 10 seconds after finger placement should be disregarded as the algorithm stabilizes.

**SGP30 (eCO2/TVOC):** The eCO2 and TVOC values are proxy estimates derived from hydrogen and ethanol gas concentrations, not direct measurements of CO2 or individual VOC compounds. Accuracy is approximately ±15%. The sensor requires 15 seconds of warm-up after power-on and benefits from 12+ hours of continuous operation for baseline calibration. These readings are suitable for detecting trends and relative changes in air quality — not for absolute concentration measurement. This limitation must be acknowledged in any reporting context.

**MLX90614:** Measures surface temperature via non-contact infrared sensing. When aimed at a forehead, typical readings are 33–36°C (skin surface), which is lower than core body temperature (36.5–37.5°C). The dashboard labels this "Surface Temp" — never "Body Temperature." Threshold values are calibrated for skin surface readings, not core temperature.

## Alert thresholds

All thresholds are sourced from published clinical and occupational health references.

### Physiological

| Parameter | Normal | Caution | Critical | Source |
|-----------|--------|---------|----------|--------|
| SpO2 | ≥ 95% | 90–94% | < 90% | WMS 2024 Clinical Practice Guidelines |
| Heart rate (high) | ≤ 100 bpm | 101–120 bpm | > 120 bpm | AHA tachycardia definition |
| Heart rate (low) | ≥ 50 bpm | 40–49 bpm | < 40 bpm | Field medicine assessment |
| Surface temp (high) | ≤ 35.5°C | 35.6–37.0°C | > 37.0°C | Ng et al. 2005 (IR forehead thermometry) |

### Environmental

| Parameter | Normal | Caution | Critical | Source |
|-----------|--------|---------|----------|--------|
| eCO2 | < 1000 ppm | 1000–2000 ppm | > 2000 ppm | International indoor air quality guidelines |
| TVOC | < 220 ppb | 220–660 ppb | > 660 ppb | German Federal Environment Agency |
| Ambient temp (high) | ≤ 26°C | 27–30°C | > 30°C | WHO housing guidelines / ASHRAE 55 |
| Ambient temp (low) | ≥ 18°C | 15–17°C | < 15°C | WHO housing guidelines / ASHRAE 55 |
| Humidity (high) | ≤ 60% | 61–70% | > 70% | ASHRAE 55 |
| Humidity (low) | ≥ 30% | 20–29% | < 20% | ASHRAE 55 |

Ambient light (BH1750) is displayed but does not trigger alerts — light levels are contextual and do not indicate a hazard in isolation.

System state is determined by the most severe individual alert: any single CRITICAL reading makes the system state CRITICAL, regardless of how many other parameters are normal.

## Architecture

```
Sensors (I2C) → app.py (Flask) → /api/vitals (JSON) → index.html (browser, polls every 2s)
```

The system is a single-file Flask application (`app.py`) with no database, no authentication, and no external dependencies beyond the sensor libraries. This is deliberate: the system is designed for field deployment where simplicity and reliability outweigh feature richness.

Each sensor has independent mock/real toggle flags. Setting a sensor's mock flag to `True` replaces its real reader with a random-value generator, allowing dashboard development and alert logic testing without hardware connected. Mock sensors display an amber `[MOCK]` indicator on the dashboard.

## Hardware

- Raspberry Pi 4 Model B
- DFRobot Gravity MAX30102 Heart Rate & Oximeter Sensor (SEN0518) — JST connector
- MLX90614 non-contact IR temperature sensor
- SGP30 eCO2/TVOC air quality sensor
- BME280 temperature/humidity/pressure sensor
- BH1750 ambient light sensor
- Breadboard with I2C bus distribution

### Wiring

Primary I2C bus (bus 1): GPIO 2 (SDA), GPIO 3 (SCL) — carries MAX30102, MLX90614, SGP30, BME280.

Secondary I2C bus (bus 3): GPIO 17 (SDA), GPIO 27 (SCL) — carries BH1750 only. Created via device tree overlay in `/boot/firmware/config.txt`:

```
dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=17,i2c_gpio_scl=27
```

All sensors operate at 3.3V.

## Setup

### Prerequisites

- Raspberry Pi 4 with I2C enabled (`raspi-config` → Interface Options → I2C)
- Python 3.11+
- Secondary I2C bus configured (see Wiring section)

### Installation

```bash
mkdir -p ~/bio_node_v2/templates
cd ~/bio_node_v2
python3 -m venv .venv
source .venv/bin/activate

pip install flask
pip install RPi.GPIO
pip install smbus
pip install adafruit-circuitpython-sgp30
pip install adafruit-circuitpython-mlx90614
pip install adafruit-circuitpython-bme280
pip install adafruit-circuitpython-bh1750
pip install adafruit-extended-bus
```

The DFRobot MAX30102 driver (`DFRobot_BloodOxygen_S.py`) is included directly in the project root — it is not available via pip.

### Running

```bash
cd ~/bio_node_v2
source .venv/bin/activate
python app.py
```

Dashboard is accessible at `http://<pi-ip>:5000` from any device on the same network.

### Verifying sensors

```bash
i2cdetect -y 1    # should show 0x57, 0x58, 0x5a, 0x77
i2cdetect -y 3    # should show 0x23
```

Individual sensor test scripts are in `tests/`.

## Project structure

```
bio_node_v2/
├── app.py                         # main application
├── DFRobot_BloodOxygen_S.py       # MAX30102 DFRobot driver (modified)
├── templates/
│   └── index.html                 # dashboard frontend
├── tests/
│   ├── test_sgp30.py
│   ├── test_mlx90614.py
│   ├── test_max30102.py
│   ├── test_bme280.py
│   └── test_bh1750.py
└── README.md
```

## Known limitations

- **Heart rate accuracy:** The DFRobot MAX30102 module reads approximately 20–30 bpm higher than wrist-based devices (e.g., Garmin) in informal testing. This is attributed to finger pressure variation and the module's onboard algorithm. Readings are directionally correct for trend monitoring.
- **Ghost readings:** The MAX30102 may briefly report heart rate and SpO2 values when no finger is present, due to the onboard MCU holding the last valid reading. Software sanity filters reject impossible values (HR > 200, SpO2 < 70, zero values) but brief false positives may still occur.
- **SGP30 is not a CO2 sensor:** eCO2 is estimated from hydrogen/ethanol concentrations. It is not equivalent to NDIR CO2 measurement. The ~±15% accuracy makes it suitable for trend detection and threshold alerting in enclosed spaces, not for calibrated atmospheric measurement.
- **Surface temperature ≠ core body temperature:** The MLX90614 measures skin surface temperature, which runs 2–4°C below core temperature. The system cannot infer core temperature from surface readings.
- **Low-end surface temperature alerts disabled:** The low-temperature thresholds (< 28°C caution, < 30°C critical) are disabled because they trigger on room ambient temperature when the sensor is not aimed at a person. Automatic detection of "sensor aimed at skin vs. ambient" is not implemented in V2.
- **No data persistence:** Readings are not logged to disk. Each session is ephemeral. CSV logging is planned for a future version.
- **Single-user system:** The dashboard has no authentication. Anyone on the local network can view the data.

## Context

BioNode V2 is the technical evolution of a diploma/thesis project (AUTH, Electrical & Computer Engineering) that demonstrated passive physiological data acquisition and display. V2 upgrades the original concept from a display system into a threshold-based early-warning monitoring node with environmental sensing, alert logic, and a remotely accessible dashboard.

The project serves as:
- An engineering portfolio piece demonstrating embedded sensor integration, I2C bus management, and real-time web-based monitoring
- A field-medicine credibility tool relevant to Wilderness First Responder (WFR) contexts
- A prototype monitoring node for enclosed habitat environments such as the LunAres analog space habitat

## Disclaimer

This system is not a medical device. Heart rate, SpO2, and temperature readings are approximate and are not suitable for clinical diagnosis or treatment decisions. All physiological thresholds are provided for trend monitoring and early-warning purposes only. Do not rely on this system for medical care.

## License

MIT

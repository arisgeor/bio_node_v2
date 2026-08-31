# BioNode V2.1

An autonomous multi-sensor environmental and physiological monitoring node built on Raspberry Pi. BioNode logs the atmosphere of an enclosed habitat continuously and unattended, and was field-deployed for the full duration of a crewed analog space mission.

**Deployment status:** deployed in the common area of AATC Habitat 2.0 (Analog Astronaut Training Center, Poland) for the seven-day crewed analog mission **AAT-112, 24–31 July 2026**, six crew. Logged **302,227 readings** over a 168-hour mission window at **99.85% logging uptime**, with **zero data lost to a real in-mission sensor fault**.

> This branch (`v2.1-logging`) is the as-flown configuration. The `main` branch is the earlier bench prototype: five sensors, proxy eCO₂ only, no persistence. If you want the system described in the paper, you are in the right place.

---

## What it does

Six sensors on two I²C buses are read every 2 seconds by a headless logger process and written to a local time-stamped SQLite database. A separate Flask process serves a live dashboard that reads the most recent database record — it never touches the I²C bus, so the display cannot contend with acquisition or stall it.

The scientific target is the shared habitat atmosphere: whether a single, centrally placed, low-cost node can resolve crew occupancy rhythms directly from the air, and whether it can run reliably for a whole mission without intervention.

## Architecture

```
                    ┌──────────────────────────────┐
   I²C bus 1 ──────►│                              │
   (hardware,25kHz) │   logger.py  (headless)      │
   SCD30            │   - reads all sensors @ 0.5Hz│
   MLX90614         │   - per-sensor try/except    │───► SQLite
   MAX30102         │   - NULL on fault, continue  │     readings
                    │                              │     events
   I²C bus 3 ──────►│   systemd: Restart=always    │        │
   (software GPIO)  └──────────────────────────────┘        │
   SGP30                                                    │
   BME280                                                   │
   BH1750            ┌──────────────────────────────┐       │
                     │   monitor.py  (Flask)        │◄──────┘
                     │   - reads latest DB row only │
                     │   - no bus access            │───► browser
                     │   - activity event markers   │     (LAN, :5001)
                     │   systemd: Restart=on-failure│
                     └──────────────────────────────┘
```

The logger/monitor split is the central design decision. Acquisition owns the bus exclusively; the dashboard is a read-only consumer of the database. A crashed or restarted dashboard cannot interrupt logging.

**Process supervision:** both run as systemd units. `bionode-logger.service` uses `Restart=always` with a 15 s backoff and a 20 s pre-start delay for bus settling; `bionode-monitor.service` is ordered `After=` the logger and restarts on failure. Every restart during the mission was automatic and was written to the events table.

## Sensors (as flown)

| Sensor | Measurement | Bus | Notes |
|--------|-------------|-----|-------|
| **SCD30** | **CO₂ (NDIR)**, temperature, relative humidity | 1 | Primary CO₂. True NDIR, not a proxy. Clock-stretching. |
| MLX90614 | Surface temperature (non-contact IR) | 1 | |
| BME280 | Temperature, relative humidity, barometric pressure | 3 | Redundant temp/RH against SCD30. Moved to software bus during bring-up. |
| SGP30 | TVOC (+ eCO₂, demoted to proxy) | 3 | |
| BH1750 | Illuminance | 3 | |
| MAX30102 (DFRobot SEN0518) | Heart rate, SpO₂ | 1 | Contact-only spot readings; blank when unattended |

**Bus allocation was derived empirically, not guessed.** At a 2 s cadence the SCD30 and SGP30 were observed to interfere — alternating readings where one channel had data and the other did not. The fault was diagnosed by row-by-row comparison establishing that the two channels were *mutually exclusive* rather than *jointly absent*, which distinguishes bus contention from a shared upstream failure. Resolution: move the TVOC sensor to the software bus. The final layout places the clock-stretching SCD30 with the two most timing-tolerant sensors on the primary hardware bus, and the three most timing-sensitive sensors on the software bus. Primary bus baudrate is reduced to 25 kHz (`dtparam=i2c_arm_baudrate=25000`) to accommodate SCD30 clock stretching. All six sensors read cleanly in this configuration.

Secondary software bus via device tree overlay:
```
dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=17,i2c_gpio_scl=27
```

## Reliability design

Each sensor is read inside its own error boundary. A sensor that fails to respond returns NULL for its channels; the logger writes the row and continues at cadence. No single sensor fault can stall the loop, block the bus, or halt the record. Impossible values are rejected at source. Power loss triggers automatic restart via systemd, and the restart is logged as an event.

Temperature and relative humidity are measured **redundantly** by both the SCD30 and the BME280. This was designed in before the mission and is the reason a hardware fault cost no continuity.

## Mission results — AAT-112

**Window:** MT 00:00 mission day 1 (24 July 2026, 07:00 UTC) → same instant seven days later (31 July, 07:00 UTC). Exactly 168 hours, an integer number of day-cycles aligned to the crew's own clock, so the diurnal analysis is not distorted by a partial day. Pre-seal setup data is archived separately rather than discarded, and is available as an empty-habitat baseline.

### Field reliability

| Metric | Value | Definition |
|---|---|---|
| Readings logged | **302,227** | rows in the mission window |
| Effective logging rate | **99.9%** | 302,227 ÷ (604,800 s ÷ 2 s) = 302,227 ÷ 302,400 |
| Logging uptime | **99.85%** | 1 − (summed gaps > 10 s ÷ window). Total gap 15.4 min over 168 h |
| Unexplained gaps | **0** | every gap > 10 s matched a logged restart in the events table |
| Data lost to sensor fault | **0** | |

Per-sensor coverage: four sensors at 100%; the CO₂ suite at 96.0% (NDIR per-sample data-ready gating, not a fault); the pressure/humidity sensor at 70.9%.

**The one real fault.** The BME280 became intermittent from mission day two and was absent for a single continuous span of **48.9 hours** before spontaneously recovering. The fail-soft architecture contained it to one non-critical channel — barometric pressure. Because temperature and humidity were measured redundantly by the SCD30, continuity of both was preserved. The remaining five sensors and the logging rate were unaffected. All five brief restarts across the mission auto-recovered and were logged.

### Environmental findings

- CO₂ ranged 645–1719 ppm (mean 828, SD 88), above the 1000 ppm comfort guideline during only 3.7% of the mission, far below occupational limits throughout — consistent with continuous ventilation.
- A repeatable diurnal cycle of ≈236 ppm peak-to-trough amplitude.
- Common-area CO₂ fell by a mean of 100 ppm during crew sleep, **on all seven nights** (paired *t*-test, p = 0.0004) — a clear atmospheric signature of collective occupancy. Sleep mean 744 ppm vs. active 843 ppm; the sleep value matches the independent diurnal trough (721 ppm), two methods converging.
- Discrete short events (individual meals) produced **no** consistent signature. This is a property of the environment, not instrument insensitivity: continuous ventilation flushes a ~30-minute load before it accumulates, while multi-hour occupancy changes reach a genuinely different steady state. The dichotomy delineates what single-zone habitat monitoring can and cannot resolve.

### Calibration note

The SCD30 reads ≈2.5 °C warmer than the independent BME280, computed as the mean difference between the two temperature channels over the window and consistent with the datasheet's documented self-heating. Ambient temperature is therefore reported from the cooler, independent sensor.

## Known limitations

- **SGP30 eCO₂ is not a CO₂ measurement.** It is estimated from hydrogen and ethanol concentrations, ≈±15% accuracy. Retained only as a secondary trend channel and labelled PROXY on the dashboard. All CO₂ results come from the SCD30 NDIR sensor.
- **Surface temperature ≠ core temperature.** The MLX90614 measures skin surface temperature, typically 2–4 °C below core. The system cannot infer core temperature.
- **Ventilation rate was not instrumented.** The ventilation time-constant interpretation of the meal null result is physically well-motivated and consistent with the data, but was not independently verified by direct air-exchange measurement.
- **Single-zone.** One centrally placed node samples the well-mixed common-area atmosphere. It cannot localize sources or resolve gradients between modules.
- **Physiological channels are spot readings.** HR/SpO₂ require finger contact and are blank when unattended; they are not a continuous mission record. The DFRobot module runs its own PPG algorithm on an onboard MCU — this host does not perform signal processing. Readings run high against wrist-based devices and the module can briefly hold a stale value with no finger present; sanity filters reject impossible values but brief false positives remain possible.
- **No authentication.** Anyone on the local network can view the dashboard.

## Setup

<details>
<summary>Hardware, wiring, installation</summary>

**Hardware:** Raspberry Pi 4 Model B · SCD30 NDIR CO₂ · SGP30 TVOC · BME280 · BH1750 · MLX90614 · DFRobot Gravity MAX30102 (SEN0518). All sensors at 3.3 V.

**Wiring:** primary I²C bus 1 on GPIO 2/3 (SCD30, MLX90614, MAX30102); software bus 3 on GPIO 17/27 (SGP30, BME280, BH1750). Apply the overlay and baudrate lines from `MISSION_config.txt` to `/boot/firmware/config.txt`.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install flask adafruit-blinka adafruit-extended-bus \
  adafruit-circuitpython-scd30 adafruit-circuitpython-sgp30 \
  adafruit-circuitpython-mlx90614 adafruit-circuitpython-bme280 \
  adafruit-circuitpython-bh1750
sqlite3 data/aat112_mission.db < schema.sql   # logger auto-creates this on first run if absent
```

The DFRobot driver (`DFRobot_BloodOxygen_S.py`) is vendored in the project root; it is not on PyPI.

**Verify:** `i2cdetect -y 1` and `i2cdetect -y 3`. Per-sensor test scripts in `tests/`.

**Run:** install `bionode-logger.service` and `bionode-monitor.service` to `/etc/systemd/system/`, then `systemctl enable --now`. Dashboard on port **5001** (`app.py`, the pre-mission single-process build, used 5000).

</details>

## Project structure

```
logger.py                  # headless acquisition → SQLite
monitor.py                 # Flask dashboard (DB reader, no bus access)
schema.sql                 # readings + events tables
frc.py                     # SCD30 forced recalibration
hr_logger.py / hr_monitor.py
app.py                     # single-process bench build (pre-mission)
DFRobot_BloodOxygen_S.py   # vendored MAX30102 driver
bionode-logger.service     # systemd units
bionode-monitor.service
MISSION_config.txt         # as-flown /boot/firmware/config.txt
templates/index.html
tests/                     # per-sensor verification scripts
```

## Publications

- **Accepted conference poster** — *Continuous Environmental Monitoring of a Crewed Analog Habitat with a Low-Cost Sensor Node: Diurnal CO₂ Dynamics and Field Reliability.* IXth Space Resources Conference, AGH University of Krakow, 3–4 September 2026, poster P55.
- **Manuscript in preparation** — A. Georgoulas, A. Kołodziejczyk, M. Harasymczuk.

All environmental data were recorded to the local database and are available from the authors. Crew activity, sleep and meal records used for Mission-Time alignment were collected as part of AAT-112 operations; all participant-derived data are used in anonymized, aggregate form.

## Future work

Distributed multi-node network for spatial resolution of sources and gradients; validated portable operation (battery with simultaneous charging, already bench-validated) for mobile survey and platform-mounted deployment; longer campaigns to establish how far these signatures generalize across crews, seasons and ventilation regimes.

## Disclaimer

This system is not a medical device. Physiological readings are approximate and are not suitable for clinical diagnosis or treatment decisions. All thresholds are for trend monitoring and early warning only.

## License

MIT
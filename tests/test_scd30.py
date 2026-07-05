#!/usr/bin/env python3
"""
SCD30 bring-up + mission-config test  --  BioNode V2.1
======================================================

PURPOSE
    Confirm the SCD30 (NDIR CO2 + onboard SHT31 temp/RH) is wired, detected on
    I2C bus 1 at 0x61, and returning sane data -- THEN apply the mission-critical
    config (ASC off, altitude comp) and stream readings so you can watch stability
    BEFORE wiring it into the logger. Fail fast: confirm clean output here first.

WIRING (Pi 4, hardware I2C bus 1)
    SCD30 VIN/VDD -> 3V3 (pin 1)   [Adafruit/most breakouts accept 3.3-5V; CHECK YOUR BOARD]
    SCD30 GND     -> GND  (pin 6)
    SCD30 SDA     -> GPIO2 / SDA (pin 3)
    SCD30 SCL     -> GPIO3 / SCL (pin 5)

    >>> WIRING SAFETY (you have killed two sensors on power mistakes) <<<
    Verify EVERY wire against the labels on the board BEFORE applying power.
    Reversed VIN/GND on these sensors = dead board in seconds. No exceptions.

KNOWN GOTCHA -- I2C CLOCK STRETCHING
    The SCD30 stretches the I2C clock. The Pi's HARDWARE I2C (bus 1) handles this
    imperfectly. If you see intermittent CRC / read errors below, the sensor is
    almost certainly FINE -- do NOT declare it dead. Fixes, in order:
      1) Slow bus 1: add `dtparam=i2c_baudrate=50000` (try 10000 if still flaky)
         to /boot/firmware/config.txt, then reboot. (Python `frequency=` is
         IGNORED on the Pi -- it must be config.txt.)
      2) Last resort: move the SCD30 to a software I2C bus, same pattern as the
         BH1750 on bus 3 (dtoverlay=i2c-gpio + ExtendedI2C).
    This script COUNTS read errors so you can see how bad it actually is.

RUN
    source ~/bio_node_v2/.venv/bin/activate
    pip install adafruit-circuitpython-scd30      # if not already installed
    python3 scd30_test.py

DEPENDENCIES
    adafruit-circuitpython-scd30, adafruit-blinka
"""

import time
import datetime

# --- Mission config (edit here) ------------------------------------------
ALTITUDE_M    = 70      # Pila site ~70 m. SCD30 uses this for pressure comp.
DISABLE_ASC   = True    # CRITICAL for a sealed habitat: ASC drags the baseline to
                        # the observed minimum. In a sealed chamber CO2 may never
                        # hit ~400 ppm, so ASC would silently UNDER-report all week.
                        # Off = trust factory cal (do an FRC in fresh outdoor air
                        # before deploy -- see footer).
MEAS_INTERVAL = 2       # seconds; SCD30 minimum is 2 s.
PRINT_EVERY   = 2       # seconds between console prints.
# -------------------------------------------------------------------------

# I2C bus 1 (standard Pi hardware I2C). board.I2C() == bus 1 on a Pi.
# To match the rest of your codebase you can instead use:
#   from adafruit_extended_bus import ExtendedI2C as I2C
#   i2c = I2C(1)
import board
import adafruit_scd30


def ts():
    return datetime.datetime.now().strftime("%H:%M:%S")


def main():
    print(f"[{ts()}] Initialising I2C bus 1 and SCD30 (expect 0x61)...")
    try:
        i2c = board.I2C()                  # bus 1: GPIO2=SDA, GPIO3=SCL
        scd = adafruit_scd30.SCD30(i2c)
    except Exception as e:
        print("\n!! Could not initialise the SCD30.")
        print(f"   Error: {type(e).__name__}: {e}")
        print("   Checklist:")
        print("     - `i2cdetect -y 1` -- is 0x61 present? (no = wiring/power)")
        print("     - VIN/GND not reversed? SDA->pin3, SCL->pin5?")
        print("     - If 0x61 shows but init hangs/errors -> clock stretching")
        print("       (slow bus 1 in config.txt -- see header).")
        return

    # --- Apply mission config, then read it back to CONFIRM it stuck ----------
    try:
        scd.self_calibration_enabled = not DISABLE_ASC    # False = ASC OFF
        scd.altitude = ALTITUDE_M
        scd.measurement_interval = MEAS_INTERVAL
        time.sleep(0.5)
        print(f"[{ts()}] Config applied:")
        print(f"     ASC (auto self-cal) : {scd.self_calibration_enabled}  "
              f"(want False for the mission)")
        print(f"     Altitude comp       : {scd.altitude} m")
        print(f"     Measurement interval: {scd.measurement_interval} s")
    except Exception as e:
        print(f"[{ts()}] WARNING: could not read/write config: "
              f"{type(e).__name__}: {e}  (often clock stretching -- see header)")

    print(f"\n[{ts()}] Streaming. NDIR needs ~1-2 min to settle -- early CO2 "
          f"values may read high/unstable. Ctrl+C to stop.\n")

    reads_ok = 0
    reads_err = 0
    last_print = 0.0

    try:
        while True:
            try:
                if scd.data_available:
                    co2  = scd.CO2                  # ppm
                    temp = scd.temperature          # deg C  (onboard SHT31)
                    rh   = scd.relative_humidity    # %RH    (onboard SHT31)
                    reads_ok += 1
                    now = time.monotonic()
                    if now - last_print >= PRINT_EVERY:
                        last_print = now
                        print(f"[{ts()}] CO2 {co2:7.1f} ppm | "
                              f"T {temp:5.2f} C | RH {rh:5.2f} % | "
                              f"ok={reads_ok} err={reads_err}")
            except RuntimeError as e:
                # CRC / transient I2C read error -- count it, keep going.
                reads_err += 1
                if reads_err <= 5 or reads_err % 20 == 0:
                    print(f"[{ts()}] read error #{reads_err} ({e}) "
                          f"-- likely clock stretching, NOT a dead sensor")
            time.sleep(0.2)
    except KeyboardInterrupt:
        total = reads_ok + reads_err
        rate = (100.0 * reads_err / total) if total else 0.0
        print(f"\n[{ts()}] Stopped. ok={reads_ok} err={reads_err} "
              f"({rate:.1f}% errors).")
        if rate > 2.0:
            print("   >2% read errors -> slow bus 1 in config.txt "
                  "(i2c_baudrate=50000, then 10000). See header.")
        else:
            print("   Error rate is low. SCD30 is good to wire into the logger.")


# =========================================================================
# FORCED RECALIBRATION (FRC) -- DO NOT run casually. Read this.
# =========================================================================
# FRC sets the sensor's reference against a KNOWN CO2 concentration. Fresh
# outdoor air is ~400-420 ppm. Running FRC indoors (elevated CO2) will
# MIS-calibrate the sensor and corrupt your whole dataset.
#
# Correct procedure, ONCE, shortly before deployment:
#   1. Take the powered sensor OUTSIDE into fresh moving air (not near people,
#      exhaust, or your own breath).
#   2. Let it run ~2-3 minutes so readings stabilise.
#   3. Then, in a Python shell:
#          scd.forced_recalibration_reference = 400
#   4. Confirm subsequent readings sit near ~400-420 ppm outdoors.
#
# Leave it commented. Do it deliberately, not as part of this test run.
# -------------------------------------------------------------------------

if __name__ == "__main__":
    main()

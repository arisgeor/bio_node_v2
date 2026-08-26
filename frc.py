import time
import board
import busio
import adafruit_scd30

i2c = busio.I2C(board.SCL, board.SDA)
scd = adafruit_scd30.SCD30(i2c)

# Make sure ASC is OFF before FRC (they're mutually exclusive approaches)
scd.self_calibration_enabled = False

print("Stabilizing in fresh outdoor air. Watch the value settle...")
print("Do NOT breathe near the sensor. Wait for it to plateau.")
for i in range(90):  # ~3 minutes of readings
    if scd.data_available:
        print(f"CO2: {scd.CO2:.1f} ppm  |  T: {scd.temperature:.1f}  RH: {scd.relative_humidity:.1f}")
    time.sleep(2)

# Once the readings have plateaued and look stable in outdoor air:
input("Press Enter to set FRC reference to 420 ppm (only if readings are stable outdoors)...")
scd.forced_recalibration_reference = 420
print(f"FRC set. Reference is now: {scd.forced_recalibration_reference} ppm")
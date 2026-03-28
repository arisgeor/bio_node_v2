# ~/bio_node_v2/test_sgp30.py
import time
import board
import busio
import adafruit_sgp30

i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
sgp30 = adafruit_sgp30.Adafruit_SGP30(i2c)

sgp30.iaq_init()

print("SGP30 serial:", [hex(i) for i in sgp30.serial])
print("Warming up (15s)...")
time.sleep(15)

for i in range(50):
    eco2, tvoc = sgp30.iaq_measure()
    print(f"eCO2: {eco2} ppm | TVOC: {tvoc} ppb")
    time.sleep(0.5)
import time
import board
import busio
from adafruit_bme280 import basic as adafruit_bme280

i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
bme = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=0x77)

for i in range(20):
    print(f"Temp: {bme.temperature:.1f} °C | Humidity: {bme.relative_humidity:.1f} % | Pressure: {bme.pressure:.1f} hPa")
    time.sleep(0.5)
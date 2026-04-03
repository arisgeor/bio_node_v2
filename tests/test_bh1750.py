import time
import board
import busio
import adafruit_bh1750

i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
bh = adafruit_bh1750.BH1750(i2c, address=0x23)

for i in range(20):
    print(f"Light: {bh.lux:.1f} lux")
    time.sleep(0.5)
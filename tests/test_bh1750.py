import time
from adafruit_extended_bus import ExtendedI2C
import adafruit_bh1750

i2c3 = ExtendedI2C(3)
bh = adafruit_bh1750.BH1750(i2c3, address=0x23)

for i in range(10):
    print(f"Light: {bh.lux:.1f} lux")
    time.sleep(0.5)
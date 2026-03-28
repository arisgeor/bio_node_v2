import time
import board
import busio
import adafruit_mlx90614

i2c = busio.I2C(board.SCL, board.SDA, frequency=100000)
mlx = adafruit_mlx90614.MLX90614(i2c)

for i in range(20):
    ambient = mlx.ambient_temperature
    obj = mlx.object_temperature
    print(f"Ambient: {ambient:.1f} °C | Object: {obj:.1f} °C")
    time.sleep(0.5)
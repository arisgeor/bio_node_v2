import time
import sys
sys.path.insert(0, '/home/aris/bio_node_v2')
from DFRobot_BloodOxygen_S import DFRobot_BloodOxygen_S_i2c

sensor = DFRobot_BloodOxygen_S_i2c(bus=1, addr=0x57)

while not sensor.begin():
    print("Sensor init failed, retrying...")
    time.sleep(1)

print("Sensor initialized. Place your finger on the sensor.")
print("Waiting 4 seconds for first reading...")
time.sleep(4)

sensor.sensor_start_collect()

for i in range(30):
    sensor.get_heartbeat_SPO2()
    print(f"HR: {sensor.heartbeat} bpm | SpO2: {sensor.SPO2} %")
    time.sleep(1)
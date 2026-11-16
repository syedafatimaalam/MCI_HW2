import serial
import time

PORT = "/dev/ttyACM0"
BAUD = 230400

ser = serial.Serial(PORT, BAUD, timeout=1)

print("Connected to", PORT)
print("Waiting for STM32 data...")

time.sleep(1)

data = ser.read(100)

print("Bytes received:", len(data))
print("Raw data:", data.hex(" "))

ser.close()
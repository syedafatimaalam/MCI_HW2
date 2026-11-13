import numpy as np
import matplotlib.pyplot as plt

# Read the captured ADC samples
samples = np.fromfile("adc_samples.bin", dtype="<u2")

# Sampling frequency = 10 kHz
fs = 10000

# Convert ADC values to voltage
voltage = samples * 3.3 / 4095

# Time axis in milliseconds
time = np.arange(len(samples)) / fs * 1000

# Plot the waveform
plt.figure(figsize=(10, 5))
plt.plot(time, voltage)

plt.title("STM32 Oscilloscope - Captured Waveform")
plt.xlabel("Time (ms)")
plt.ylabel("Voltage (V)")
plt.grid(True)
plt.tight_layout()

print("First 10 ADC samples:", samples[:10])
print("Maximum ADC reading:", samples.max())
plt.show()

# Print measurements
print("Samples:", len(samples))
print("Maximum voltage:", round(np.max(voltage), 3), "V")
print("Minimum voltage:", round(np.min(voltage), 3), "V")
print("Peak-to-peak voltage:", round(np.ptp(voltage), 3), "V")
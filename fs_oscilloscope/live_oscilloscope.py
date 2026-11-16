import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# UART configuration
PORT = "/dev/ttyACM0"
BAUD = 230400

# ADC configuration
FS = 10000
VREF = 3.3
ADC_MAX = 4095

# Display configuration
N = 1000
PACKET_SAMPLES = 100
PACKET_SIZE = 204

HEADER = b"\xFF\xFF"

# Open UART
ser = serial.Serial(PORT, BAUD, timeout=0)

# UART receiving buffer
rx_buffer = bytearray()

# Waveform buffer
samples = np.zeros(N, dtype=np.uint16)

# Packet statistics
last_packet = None
lost_packets = 0
bad_packets = 0

# Plot setup
fig, ax = plt.subplots(figsize=(11, 5))

time_ms = np.arange(N) / FS * 1000

line, = ax.plot(
    time_ms,
    np.zeros(N),
    linewidth=1.5
)

ax.set_xlim(0, 100)
ax.set_ylim(0, 3.3)

ax.set_xlabel("Time (ms)")
ax.set_ylabel("Voltage (V)")
ax.grid(True)


def update(frame):
    global rx_buffer
    global samples
    global last_packet
    global lost_packets
    global bad_packets

    # Receive available UART bytes.
    waiting = ser.in_waiting

    if waiting:
        rx_buffer.extend(ser.read(waiting))

    # Process complete packets.
    while True:

        start = rx_buffer.find(HEADER)

        if start == -1:
            # Keep a possible partial header.
            if rx_buffer[-1:] == b"\xFF":
                rx_buffer = bytearray(b"\xFF")
            else:
                rx_buffer.clear()
            break

        # Discard bytes before header.
        if start > 0:
            del rx_buffer[:start]

        # Wait until complete packet arrives.
        if len(rx_buffer) < PACKET_SIZE:
            break

        # Extract packet.
        packet = bytes(rx_buffer[:PACKET_SIZE])

        packet_number = packet[2]
        payload = packet[3:203]
        received_checksum = packet[203]

        # Calculate checksum.
        checksum = packet_number

        for byte in payload:
            checksum ^= byte

        # Decode ADC samples.
        new_samples = np.frombuffer(
            payload,
            dtype="<u2"
        )

        # Reject corrupted packets.
        if (
            checksum != received_checksum
            or np.any(new_samples > ADC_MAX)
        ):
            bad_packets += 1

            # Search for next valid header.
            del rx_buffer[0]
            continue

        # Valid packet received.
        del rx_buffer[:PACKET_SIZE]

        # Check for missing packets.
        if last_packet is not None:
            expected = (last_packet + 1) % 256

            if packet_number != expected:
                missing = (packet_number - expected) % 256
                lost_packets += missing

        last_packet = packet_number

        # Update rolling waveform.
        samples = np.roll(
            samples,
            -PACKET_SAMPLES
        )

        samples[-PACKET_SAMPLES:] = new_samples

    # Convert ADC readings to voltage.
    voltage = samples * VREF / ADC_MAX

    # Update waveform.
    line.set_ydata(voltage)

    # Measurements.
    vpp = np.ptp(voltage)

    ax.set_title(
        f"STM32 Live Oscilloscope | "
        f"Vpp: {vpp:.2f} V | "
        f"Missing packets: {lost_packets} | "
        f"Bad packets: {bad_packets}"
    )

    return line,


ani = FuncAnimation(
    fig,
    update,
    interval=50,
    blit=False,
    cache_frame_data=False
)

try:
    plt.show()
finally:
    ser.close()
"""SIFASCOPE — STM32F3 Discovery live oscilloscope.

Dependencies (Ubuntu): python3-pyqt5 python3-pyqtgraph python3-serial python3-numpy
Firmware packet layout (204 bytes):
    0xFF 0xFF | sequence:uint8 | 100 x uint16_le (12-bit ADC) | XOR:uint8
UART: 230400 baud, 8N1.  ADC: 10,000 samples/s, Vref: 3.3 V.

No STM32 firmware changes are required if the existing synchronized-packet
main.c is installed. All coupling / trigger / measurement features here are
software-side; AC coupling does not alter the board's input voltage limits.
"""

import csv
import os
import sys
from collections import deque

import numpy as np
import serial
from serial.tools import list_ports
from PyQt5 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

FS = 10_000
BAUD = 230_400
VREF = 3.3
ADC_TOP = 4095
PACKET_SAMPLES = 100
PACKET_BYTES = 204
HEADER = b"\xFF\xFF"
HISTORY_SAMPLES = 30_000  # 3 s of recent measurements

C = {
    "bg": "#fff8fc", "card": "#fffefe", "pink": "#f7bfdc",
    "lavender": "#dfd0fa", "purple": "#7251a6", "deep": "#483b61",
    "text": "#4b405c", "muted": "#84758f", "border": "#ecdaf3",
    "screen": "#171323", "grid": "#756980", "wave": "#ffdb8c",
    "mint": "#8be6c4", "danger": "#a94772",
}

STYLE = """
QMainWindow, QWidget#root { background: #fff8fc; }
QFrame#card { background: #fffefe; border: 1px solid #ecdaf3; border-radius: 16px; }
QFrame#header { background: #f2e7fc; border: 1px solid #e5d3fa; border-radius: 16px; }
QLabel { color: #4b405c; font-size: 12px; }
QLabel#brand { color: #7251a6; font-size: 29px; font-weight: 900; }
QLabel#caption { color: #84758f; font-size: 12px; }
QLabel#section { color: #7251a6; font-size: 14px; font-weight: 800; }
QLabel#value { color: #59467c; font-size: 17px; font-weight: 800; }
QLabel#status { color: #6b5b78; font-size: 11px; }
QPushButton { background: #f0e3fb; border: 1px solid #e2cef5; border-radius: 9px;
              color: #574471; font-weight: 650; padding: 8px 11px; min-height: 20px; }
QPushButton:hover { background: #e4d0f9; }
QPushButton:pressed { background: #d3b5f0; }
QPushButton#primary { background: #f7bfdc; border-color: #eeadd0; color: #663851; }
QPushButton#primary:hover { background: #f4aace; }
QPushButton#danger { background: #fae5ef; color: #a94772; }
QPushButton:disabled { color: #ada0b3; background: #f8f4f8; }
QComboBox, QDoubleSpinBox, QSpinBox { background: white; border: 1px solid #ead9f1;
                     border-radius: 8px; padding: 6px; color: #4b405c; min-height: 21px; }
QComboBox QAbstractItemView { background: white; color: #4b405c; selection-background-color: #edd5f7; }
QCheckBox { color: #584867; spacing: 6px; }
QCheckBox::indicator { width: 15px; height: 15px; }
QSlider::groove:horizontal { height: 7px; border-radius: 3px; background: #f1e4f7; }
QSlider::handle:horizontal { background: #b78cde; width: 15px; margin: -5px 0; border-radius: 7px; }
QListWidget { border: 1px solid #eddef3; border-radius: 10px; background: #fffbfd;
              color: #59467c; padding: 3px; }
QListWidget::item { padding: 4px; }
QListWidget::item:selected { background: #f4e1f5; color: #59467c; border-radius: 5px; }
QScrollArea { border: none; background: transparent; }
"""


def make_label(text, ident=None):
    label = QtWidgets.QLabel(text)
    if ident:
        label.setObjectName(ident)
    return label


def section(title, parent_layout):
    label = make_label(title, "section")
    parent_layout.addWidget(label)
    return label


def row(*widgets):
    layout = QtWidgets.QHBoxLayout()
    layout.setSpacing(7)
    for widget in widgets:
        if widget is None:
            layout.addStretch(1)
        elif isinstance(widget, QtWidgets.QLayout):
            layout.addLayout(widget)
        else:
            layout.addWidget(widget)
    return layout


class SifaScope(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SIFASCOPE | STM32 Digital Oscilloscope")
        self.resize(1450, 860)
        self.setMinimumSize(1060, 660)
        self.setStyleSheet(STYLE)

        self.ser = None
        self.rx = bytearray()
        self.history = deque(maxlen=HISTORY_SAMPLES)
        self.last_sequence = None
        self.total_packets = 0
        self.missing_packets = 0
        self.bad_packets = 0
        self.paused = False
        self.single_armed = False
        self.view_raw = np.array([], dtype=np.uint16)
        self.view_v = np.array([], dtype=np.float64)
        self.view_t = np.array([], dtype=np.float64)
        self.measurement_keys = ["Frequency", "Amplitude", "Max", "Min"]
        self.last_error = ""

        self._build_ui()
        self.refresh_ports()
        self.refresh_measurements()
        self._axis_changed()

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(35)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def _card(self, outer, stretch=0):
        frame = QtWidgets.QFrame()
        frame.setObjectName("card")
        box = QtWidgets.QVBoxLayout(frame)
        box.setContentsMargins(15, 14, 15, 14)
        box.setSpacing(9)
        outer.addWidget(frame, stretch)
        return box

    def _build_ui(self):
        root = QtWidgets.QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        body = QtWidgets.QVBoxLayout(root)
        body.setContentsMargins(16, 14, 16, 10)
        body.setSpacing(10)

        head = QtWidgets.QFrame()
        head.setObjectName("header")
        hb = QtWidgets.QHBoxLayout(head)
        hb.setContentsMargins(19, 10, 19, 10)
        brand_box = QtWidgets.QVBoxLayout()
        brand_box.setSpacing(0)
        brand_box.addWidget(make_label("SIFASCOPE", "brand"))
        brand_box.addWidget(make_label("STM32F3 Digital Oscilloscope", "caption"))
        hb.addLayout(brand_box)
        hb.addStretch()
        hb.addWidget(make_label("UART 230400  •  ADC 12-bit  •  10 kSa/s", "caption"))
        body.addWidget(head)

        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(11)
        body.addLayout(layout, stretch=1)

        # Left controls inspired by the reference's prominent sidebar.
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setFixedWidth(300)
        left = QtWidgets.QWidget()
        left.setStyleSheet("background: transparent;")
        side = QtWidgets.QVBoxLayout(left)
        side.setContentsMargins(0, 0, 4, 0)
        side.setSpacing(10)
        scroll.setWidget(left)
        layout.addWidget(scroll)

        conn = self._card(side)
        section("01  CONNECTION", conn)
        self.port = QtWidgets.QComboBox()
        self.port.setEditable(True)
        self.port.setToolTip("Virtual COM port; normally /dev/ttyACM0")
        self.refresh_button = QtWidgets.QPushButton("↻  Refresh ports")
        conn.addWidget(make_label("Serial port"))
        conn.addWidget(self.port)
        conn.addWidget(self.refresh_button)
        self.connect_button = QtWidgets.QPushButton("Connect")
        self.connect_button.setObjectName("primary")
        conn.addWidget(self.connect_button)
        self.connection_state = make_label("●  Disconnected", "caption")
        conn.addWidget(self.connection_state)

        horiz = self._card(side)
        section("02  HORIZONTAL  ·  TIME", horiz)
        self.time_window = QtWidgets.QComboBox()
        for value in (10, 20, 50, 100, 200, 500, 1000):
            self.time_window.addItem(f"{value} ms window", value)
        self.time_window.setCurrentIndex(3)
        horiz.addWidget(self.time_window)
        zoom_out = QtWidgets.QPushButton("−  Zoom out")
        zoom_in = QtWidgets.QPushButton("+  Zoom in")
        horiz.addLayout(row(zoom_out, zoom_in))
        horiz.addWidget(make_label("Mouse wheel over graph also zooms", "caption"))
        zoom_in.clicked.connect(lambda: self._change_zoom(-1))
        zoom_out.clicked.connect(lambda: self._change_zoom(1))

        vert = self._card(side)
        section("03  VERTICAL  ·  VOLTAGE", vert)
        self.volt_div = QtWidgets.QComboBox()
        for volts in (0.1, 0.2, 0.5, 1.0, 2.0):
            self.volt_div.addItem(f"{volts:g} V/div", volts)
        self.volt_div.setCurrentIndex(3)
        self.vert_center = QtWidgets.QDoubleSpinBox()
        self.vert_center.setDecimals(2)
        self.vert_center.setRange(-10, 10)
        self.vert_center.setSingleStep(0.1)
        self.vert_center.setValue(1.65)
        self.vert_center.setSuffix(" V")
        vert.addWidget(make_label("Vertical scale"))
        vert.addWidget(self.volt_div)
        vert.addWidget(make_label("Vertical center"))
        vert.addWidget(self.vert_center)
        vert.addWidget(make_label("Display coupling"))
        self.coupling = QtWidgets.QComboBox()
        self.coupling.addItems(["DC", "AC (display only)"])
        vert.addWidget(self.coupling)

        trig = self._card(side)
        section("04  TRIGGER", trig)
        self.trigger_mode = QtWidgets.QComboBox()
        self.trigger_mode.addItems(["OFF (free-run)", "Rising edge", "Falling edge"])
        self.trigger_level = QtWidgets.QDoubleSpinBox()
        self.trigger_level.setRange(0, VREF)
        self.trigger_level.setValue(1.65)
        self.trigger_level.setSingleStep(0.05)
        self.trigger_level.setSuffix(" V")
        trig.addWidget(self.trigger_mode)
        trig.addWidget(make_label("Trigger level"))
        trig.addWidget(self.trigger_level)
        self.trigger_status = make_label("Free running", "caption")
        trig.addWidget(self.trigger_status)

        cursors = self._card(side)
        section("05  CURSORS", cursors)
        self.cursor_check = QtWidgets.QCheckBox("Show time cursors")
        self.cursor_a = QtWidgets.QDoubleSpinBox()
        self.cursor_b = QtWidgets.QDoubleSpinBox()
        for widget, value in ((self.cursor_a, 10.0), (self.cursor_b, 30.0)):
            widget.setRange(0, 1000)
            widget.setDecimals(1)
            widget.setSuffix(" ms")
            widget.setValue(value)
        cursors.addWidget(self.cursor_check)
        cursors.addLayout(row(make_label("T1"), self.cursor_a))
        cursors.addLayout(row(make_label("T2"), self.cursor_b))
        self.cursor_delta = make_label("Δt: --", "caption")
        cursors.addWidget(self.cursor_delta)
        side.addStretch(1)

        # Main plotting and measurement area.
        main_area = QtWidgets.QVBoxLayout()
        main_area.setSpacing(10)
        layout.addLayout(main_area, stretch=1)

        toolbar_card = QtWidgets.QFrame()
        toolbar_card.setObjectName("card")
        toolbar = QtWidgets.QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(13, 9, 13, 9)
        toolbar.setSpacing(8)
        self.run_button = QtWidgets.QPushButton("⏸  Pause")
        self.single_button = QtWidgets.QPushButton("◎  Single capture")
        self.auto_button = QtWidgets.QPushButton("↗  Auto scale")
        self.csv_button = QtWidgets.QPushButton("↓  Save CSV")
        self.png_button = QtWidgets.QPushButton("▧  Screenshot")
        toolbar.addWidget(self.run_button)
        toolbar.addWidget(self.single_button)
        toolbar.addWidget(self.auto_button)
        toolbar.addStretch()
        toolbar.addWidget(self.csv_button)
        toolbar.addWidget(self.png_button)
        main_area.addWidget(toolbar_card)

        plot_card = QtWidgets.QFrame()
        plot_card.setObjectName("card")
        plot_box = QtWidgets.QVBoxLayout(plot_card)
        plot_box.setContentsMargins(12, 9, 12, 10)
        plot_box.addWidget(make_label("LIVE SIGNAL   •   CHANNEL 1", "section"))
        self.plot = pg.PlotWidget()
        self.plot.setBackground(C["screen"])
        self.plot.showGrid(x=True, y=True, alpha=0.23)
        self.plot.setLabel("bottom", "Time", units="ms", color="#f0e5fc")
        self.plot.setLabel("left", "Voltage", units="V", color="#f0e5fc")
        self.plot.getAxis("bottom").setPen(pg.mkPen("#bfaed1"))
        self.plot.getAxis("left").setPen(pg.mkPen("#bfaed1"))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen("#e6d5f4"))
        self.plot.getAxis("left").setTextPen(pg.mkPen("#e6d5f4"))
        self.plot.setXRange(0, 100, padding=0)
        self.plot.setYRange(-2.35, 5.65, padding=0)
        self.plot.setMouseEnabled(x=True, y=True)
        self.plot.setMenuEnabled(False)
        self.wave = self.plot.plot(pen=pg.mkPen(C["wave"], width=2))
        self.trigger_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#e897bc", width=1, style=QtCore.Qt.DashLine))
        self.plot.addItem(self.trigger_line)
        self.trigger_line.hide()
        self.c1 = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#ad9dff", style=QtCore.Qt.DashLine, width=1.4))
        self.c2 = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#f8a6c7", style=QtCore.Qt.DashLine, width=1.4))
        self.plot.addItem(self.c1)
        self.plot.addItem(self.c2)
        self.c1.hide()
        self.c2.hide()
        plot_box.addWidget(self.plot, stretch=1)
        main_area.addWidget(plot_card, stretch=1)

        measurement_frame = QtWidgets.QFrame()
        measurement_frame.setObjectName("card")
        measurement_box = QtWidgets.QVBoxLayout(measurement_frame)
        measurement_box.setContentsMargins(13, 11, 13, 12)
        section("MEASUREMENTS  ✦  choose what appears", measurement_box)
        chooser = QtWidgets.QHBoxLayout()
        self.measurement_picker = QtWidgets.QComboBox()
        self.measurement_picker.addItems(["Max", "Min", "Amplitude", "Frequency", "Mean", "Period", "Duty Cycle", "Vpp"])
        self.add_measurement_button = QtWidgets.QPushButton("+  Add measurement")
        self.remove_measurement_button = QtWidgets.QPushButton("−  Remove selected")
        chooser.addWidget(self.measurement_picker)
        chooser.addWidget(self.add_measurement_button)
        chooser.addWidget(self.remove_measurement_button)
        chooser.addStretch()
        measurement_box.addLayout(chooser)
        self.measurement_list = QtWidgets.QListWidget()
        self.measurement_list.setFixedHeight(55)
        self.measurement_list.setFlow(QtWidgets.QListView.LeftToRight)
        self.measurement_list.setWrapping(False)
        self.measurement_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        measurement_box.addWidget(self.measurement_list)
        self.measurement_values = QtWidgets.QLabel("Waiting for signal…")
        self.measurement_values.setObjectName("value")
        self.measurement_values.setWordWrap(True)
        measurement_box.addWidget(self.measurement_values)
        main_area.addWidget(measurement_frame)

        self.status = make_label("Ready. Select /dev/ttyACM0 and connect.", "status")
        body.addWidget(self.status)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.toggle_connection)
        self.run_button.clicked.connect(self.toggle_pause)
        self.single_button.clicked.connect(self.single_capture)
        self.auto_button.clicked.connect(self.auto_scale)
        self.csv_button.clicked.connect(self.save_csv)
        self.png_button.clicked.connect(self.save_image)
        self.add_measurement_button.clicked.connect(self.add_measurement)
        self.remove_measurement_button.clicked.connect(self.remove_measurement)
        self.time_window.currentIndexChanged.connect(self._axis_changed)
        self.volt_div.currentIndexChanged.connect(self._axis_changed)
        self.vert_center.valueChanged.connect(self._axis_changed)
        self.coupling.currentIndexChanged.connect(self._axis_changed)
        self.trigger_mode.currentIndexChanged.connect(self._axis_changed)
        self.trigger_level.valueChanged.connect(self._axis_changed)
        self.cursor_check.toggled.connect(self._cursors_changed)
        self.cursor_a.valueChanged.connect(self._cursor_spins_changed)
        self.cursor_b.valueChanged.connect(self._cursor_spins_changed)
        self.c1.sigPositionChangeFinished.connect(self._cursor_lines_changed)
        self.c2.sigPositionChangeFinished.connect(self._cursor_lines_changed)

    def refresh_ports(self):
        current = self.port.currentText()
        devices = [p.device for p in list_ports.comports() if p.device.startswith("/dev/")]
        if "/dev/ttyACM0" not in devices:
            devices.append("/dev/ttyACM0")
        ordered = sorted(set(devices), key=lambda value: (value != "/dev/ttyACM0", value))
        self.port.clear()
        self.port.addItems(ordered)
        if current and self.port.findText(current) == -1:
            self.port.addItem(current)
        self.port.setCurrentText(current or "/dev/ttyACM0")

    def toggle_connection(self):
        if self.ser:
            self.disconnect()
            return
        try:
            self.ser = serial.Serial(self.port.currentText().strip(), BAUD, timeout=0)
            self.rx.clear()
            self.history.clear()
            self.last_sequence = None
            self.total_packets = self.missing_packets = self.bad_packets = 0
            self.paused = False
            self.single_armed = False
            self.run_button.setText("⏸  Pause")
            self.connect_button.setText("Disconnect")
            self.connection_state.setText("●  Connected")
            self.status.setText(f"Connected to {self.ser.port}  •  {BAUD} baud")
        except (OSError, serial.SerialException) as exc:
            self.ser = None
            QtWidgets.QMessageBox.warning(self, "Serial port", str(exc))

    def disconnect(self):
        if self.ser:
            try:
                self.ser.close()
            except (OSError, serial.SerialException):
                pass
        self.ser = None
        self.connect_button.setText("Connect")
        self.connection_state.setText("●  Disconnected")
        self.status.setText("Disconnected  •  reconnect when ready")

    def toggle_pause(self):
        self.paused = not self.paused
        self.single_armed = False
        self.run_button.setText("▶  Resume" if self.paused else "⏸  Pause")
        if not self.paused:
            self.status.setText("Running…")

    def single_capture(self):
        if not self.ser:
            QtWidgets.QMessageBox.information(self, "Connect first", "Connect to the STM32 before single capture.")
            return
        self.single_armed = True
        self.paused = False
        self.run_button.setText("⏸  Pause")
        self.status.setText("Single capture armed — waiting for a full window of fresh samples")
        self.history.clear()

    def _change_zoom(self, offset):
        target = max(0, min(self.time_window.count() - 1, self.time_window.currentIndex() + offset))
        self.time_window.setCurrentIndex(target)

    def _axis_changed(self, *_):
        time_ms = self.time_window.currentData()
        if time_ms is None:
            return
        self.plot.setXRange(0, float(time_ms), padding=0)
        division = float(self.volt_div.currentData() or 1.0)
        center = self.vert_center.value()
        # Eight major divisions, as on an oscilloscope.
        self.plot.setYRange(center - 4 * division, center + 4 * division, padding=0)
        self.trigger_line.setValue(self.trigger_level.value())
        if self.trigger_mode.currentIndex() == 0:
            self.trigger_line.hide()
        else:
            self.trigger_line.show()
        self._cursor_spins_changed()

    def _cursors_changed(self, checked):
        for item in (self.c1, self.c2):
            item.setVisible(checked)
        self._cursor_spins_changed()

    def _cursor_spins_changed(self, *_):
        self.c1.blockSignals(True)
        self.c2.blockSignals(True)
        self.c1.setValue(self.cursor_a.value())
        self.c2.setValue(self.cursor_b.value())
        self.c1.blockSignals(False)
        self.c2.blockSignals(False)
        self.cursor_delta.setText(f"Δt: {abs(self.cursor_b.value() - self.cursor_a.value()):.2f} ms")

    def _cursor_lines_changed(self, *_):
        self.cursor_a.blockSignals(True)
        self.cursor_b.blockSignals(True)
        self.cursor_a.setValue(max(0.0, self.c1.value()))
        self.cursor_b.setValue(max(0.0, self.c2.value()))
        self.cursor_a.blockSignals(False)
        self.cursor_b.blockSignals(False)
        self.cursor_delta.setText(f"Δt: {abs(self.cursor_b.value() - self.cursor_a.value()):.2f} ms")

    def add_measurement(self):
        value = self.measurement_picker.currentText()
        if value and value not in self.measurement_keys:
            self.measurement_keys.append(value)
            self.refresh_measurements()

    def remove_measurement(self):
        item = self.measurement_list.currentItem()
        if not item:
            return
        value = item.text()
        if value in self.measurement_keys:
            self.measurement_keys.remove(value)
        self.refresh_measurements()

    def refresh_measurements(self):
        self.measurement_list.clear()
        self.measurement_list.addItems(self.measurement_keys)
        self._show_measurements()

    def _consume_packets(self):
        # Header can never appear inside a correctly encoded sample because
        # the high byte of a 12-bit sample is always <= 0x0F.
        while True:
            start = self.rx.find(HEADER)
            if start < 0:
                self.rx[:] = b"\xff" if self.rx.endswith(b"\xff") else b""
                return
            if start:
                del self.rx[:start]
            if len(self.rx) < PACKET_BYTES:
                return
            seq = self.rx[2]
            payload = bytes(self.rx[3:203])
            check = seq
            for byte in payload:
                check ^= byte
            values = np.frombuffer(payload, dtype="<u2")
            if check != self.rx[203] or np.any(values > ADC_TOP):
                self.bad_packets += 1
                del self.rx[0]
                continue
            del self.rx[:PACKET_BYTES]
            if self.last_sequence is not None:
                missing = (seq - self.last_sequence - 1) & 255
                self.missing_packets += missing
            self.last_sequence = seq
            self.total_packets += 1
            self.history.extend(values.tolist())

    def tick(self):
        if self.ser:
            try:
                n = self.ser.in_waiting
                if n:
                    self.rx.extend(self.ser.read(min(n, 65536)))
                    self._consume_packets()
                if len(self.rx) > 65536:
                    self.rx[:] = self.rx[-PACKET_BYTES:]
                self.status.setText(
                    f"● Connected: {self.ser.port}   |   Frames: {self.total_packets}   |   "
                    f"Missing: {self.missing_packets}   |   Bad: {self.bad_packets}   |   "
                    f"Sample rate: {FS:,} Sa/s"
                )
            except (OSError, serial.SerialException) as exc:
                self.disconnect()
                self.status.setText(f"Connection lost: {exc}. Reconnect when ready.")
        if self.paused:
            return
        n = int(FS * int(self.time_window.currentData() or 100) / 1000)
        if len(self.history) < max(10, n):
            return
        raw = np.fromiter(self.history, dtype=np.uint16)
        chosen = raw[-n:]
        if self.trigger_mode.currentIndex() != 0:
            expanded = raw[-min(len(raw), max(2 * n, n + 1000)):]
            v = expanded.astype(np.float64) * (VREF / ADC_TOP)
            level = self.trigger_level.value()
            rising = self.trigger_mode.currentIndex() == 1
            if rising:
                positions = np.flatnonzero((v[:-1] < level) & (v[1:] >= level))
            else:
                positions = np.flatnonzero((v[:-1] > level) & (v[1:] <= level))
            possible = positions[positions + n <= len(expanded)]
            if len(possible):
                chosen = expanded[int(possible[-1]):int(possible[-1]) + n]
                self.trigger_status.setText("● Trigger locked")
            else:
                self.trigger_status.setText("○ Waiting for edge (free-running)")
        else:
            self.trigger_status.setText("Free running")
        volts_raw = chosen.astype(np.float64) * (VREF / ADC_TOP)
        display = volts_raw.copy()
        if self.coupling.currentIndex() == 1:
            display -= np.mean(display)
        self.view_raw = chosen.copy()
        self.view_v = volts_raw.copy()
        self.view_t = np.arange(len(display), dtype=np.float64) * (1000 / FS)
        self.wave.setData(self.view_t, display)
        self._show_measurements()
        if self.single_armed:
            self.single_armed = False
            self.paused = True
            self.run_button.setText("▶  Resume")
            self.status.setText("Single capture complete — display frozen")

    @staticmethod
    def _edge_info(v):
        if len(v) < 30 or np.ptp(v) < 0.08:
            return None, None
        low, high = np.percentile(v, [5, 95])
        amplitude = high - low
        if amplitude < 0.08:
            return None, None
        # Hysteresis avoids multiple threshold crossings from modest noise.
        mid = (low + high) * 0.5
        h = min(0.12 * amplitude, 0.2)
        lo_thr, hi_thr = mid - h, mid + h
        rising = []
        armed = v[0] < lo_thr
        for i in range(1, len(v)):
            if not armed and v[i] < lo_thr:
                armed = True
            if armed and v[i] >= hi_thr:
                rising.append(i)
                armed = False
        if len(rising) < 2:
            return None, None
        gaps = np.diff(rising).astype(np.float64)
        # Exclude implausibly short glitch intervals for the intended 100–1000 Hz range.
        gaps = gaps[(gaps >= 6) & (gaps <= 500)]
        if not len(gaps):
            return None, None
        period_samples = float(np.median(gaps))
        freq = FS / period_samples
        if not (5 <= freq <= FS / 2):
            return None, None
        return freq, period_samples / FS * 1000.0

    @staticmethod
    def _duty_cycle(v, freq):
        # Duty cycle is only meaningful for roughly two-level waveforms.
        if freq is None or len(v) < 30:
            return None
        low, high = np.percentile(v, [5, 95])
        if high - low < 0.08:
            return None
        mid = (low + high) / 2
        normalized = (v - low) / (high - low)
        if np.mean((normalized > 0.2) & (normalized < 0.8)) > 0.22:
            return None  # sine/ramp: not a square-ish waveform
        return float(np.mean(v >= mid) * 100)

    def _show_measurements(self):
        if not self.measurement_keys:
            self.measurement_values.setText("No measurements selected — add one above.")
            return
        if self.view_v.size < 10:
            self.measurement_values.setText("Waiting for waveform…")
            return
        v = self.view_v
        vmax = float(np.max(v))
        vmin = float(np.min(v))
        vpp = vmax - vmin
        freq, period = self._edge_info(v)
        duty = self._duty_cycle(v, freq)
        lookup = {
            "Max": f"{vmax:.3f} V",
            "Min": f"{vmin:.3f} V",
            "Amplitude": f"{vpp / 2:.3f} V",
            "Frequency": f"{freq:.1f} Hz" if freq is not None else "—",
            "Mean": f"{np.mean(v):.3f} V",
            "Period": f"{period:.3f} ms" if period is not None else "—",
            "Duty Cycle": f"{duty:.1f}%" if duty is not None else "— (square waves)",
            "Vpp": f"{vpp:.3f} V",
        }
        self.measurement_values.setText("     ✦     ".join(f"{key}: {lookup[key]}" for key in self.measurement_keys))

    def auto_scale(self):
        if self.view_v.size < 10:
            return
        v = self.view_v.copy()
        if self.coupling.currentIndex() == 1:
            v -= np.mean(v)
        lo, hi = np.percentile(v, [1, 99])
        span = max(hi - lo, 0.2)
        target_div = span * 1.3 / 8.0
        options = [float(self.volt_div.itemData(i)) for i in range(self.volt_div.count())]
        index = next((i for i, val in enumerate(options) if val >= target_div), len(options) - 1)
        self.volt_div.setCurrentIndex(index)
        self.vert_center.setValue(float((hi + lo) / 2))

    def save_csv(self):
        if not self.history:
            QtWidgets.QMessageBox.information(self, "No data yet", "Connect the STM32 and receive samples first.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save waveform data", "SIFASCOPE_capture.csv", "CSV files (*.csv)")
        if not path:
            return
        values = np.fromiter(self.history, dtype=np.uint16)
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["sample_index", "time_ms_relative", "adc_12_bit", "voltage_v"])
                for i, value in enumerate(values):
                    writer.writerow([i, f"{i * 1000 / FS:.4f}", int(value), f"{int(value) * VREF / ADC_TOP:.6f}"])
            self.status.setText(f"Saved {len(values):,} samples to {os.path.basename(path)}")
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "CSV export failed", str(exc))

    def save_image(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save oscilloscope screenshot", "SIFASCOPE.png", "PNG images (*.png)")
        if path:
            if not self.grab().save(path, "PNG"):
                QtWidgets.QMessageBox.warning(self, "Export failed", "Could not save the screenshot.")
            else:
                self.status.setText(f"Saved screenshot to {os.path.basename(path)}")

    def closeEvent(self, event):
        self.timer.stop()
        self.disconnect()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SifaScope()
    window.show()
    sys.exit(app.exec_())

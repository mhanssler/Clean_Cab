"""
BME688 sensor driver for Arduino serial stream.

This module reads CSV lines emitted by the Arduino sketch:
`arduino/bme688_baseline_csv_megacom5/bme688_baseline_csv_megacom5.ino`
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import NamedTuple, Optional

_SERIAL_AVAILABLE = False
try:
    import serial  # type: ignore
    _SERIAL_AVAILABLE = True
except ImportError:
    serial = None


class SensorReading(NamedTuple):
    """Container for BME688 sensor readings."""

    temperature: float  # Celsius
    humidity: float  # %RH
    pressure: float  # hPa
    gas_resistance: float  # Ohms
    timestamp: float  # Unix timestamp


@dataclass
class HeaterProfile:
    """Legacy heater profile container for compatibility with existing tests."""

    temperature: int = 320
    duration_ms: int = 150


def parse_arduino_csv_line(line: str) -> Optional[SensorReading]:
    """Parse one Arduino CSV output line into a SensorReading."""

    text = line.strip()
    if not text:
        return None
    if text.startswith("#"):
        return None
    if text.lower().startswith("host_ms,"):
        return None

    parts = [part.strip() for part in text.split(",")]
    if len(parts) < 6:
        return None

    try:
        int(parts[0])  # host_ms
        int(parts[1])  # sample index
        temperature = float(parts[2])
        pressure_raw = float(parts[3])
        humidity = float(parts[4])
        gas_resistance = float(parts[5])
    except ValueError:
        return None

    # Arduino sketch emits pressure in Pa. Convert to hPa for app consistency.
    pressure_hpa = pressure_raw / 100.0 if pressure_raw > 2000 else pressure_raw

    return SensorReading(
        temperature=temperature,
        humidity=humidity,
        pressure=pressure_hpa,
        gas_resistance=gas_resistance,
        timestamp=time.time(),
    )


class BME688:
    """BME688 reader backed by Arduino serial CSV output."""

    def __init__(
        self,
        serial_port: str = "COM5",
        baudrate: int = 115200,
        timeout_seconds: float = 2.0,
        startup_delay_seconds: float = 2.0,
    ):
        if not _SERIAL_AVAILABLE:
            raise RuntimeError(
                "pyserial is not installed. Install dependencies with: pip install -r requirements.txt"
            )

        self.serial_port = serial_port
        self.baudrate = baudrate
        self.timeout_seconds = timeout_seconds
        self.startup_delay_seconds = startup_delay_seconds
        self.heater_profile = HeaterProfile()

        self._logger = logging.getLogger("SmartSniffer.Sensor")
        self._serial = serial.Serial(self.serial_port, self.baudrate, timeout=self.timeout_seconds)

        # Most Arduino boards reset when serial opens; allow time for banner/header lines.
        if self.startup_delay_seconds > 0:
            time.sleep(self.startup_delay_seconds)

    def set_heater_profile(self, temperature: int, duration_ms: int) -> None:
        """Keep API compatibility; heater is controlled in Arduino sketch, not over serial."""

        self.heater_profile.temperature = max(200, min(400, temperature))
        self.heater_profile.duration_ms = max(1, min(4032, duration_ms))
        self._logger.debug(
            "Heater profile requested (%sC, %sms), but Arduino controls heater internally.",
            self.heater_profile.temperature,
            self.heater_profile.duration_ms,
        )

    def read(self) -> SensorReading:
        """Read and parse the next valid sensor CSV row from serial."""

        if self._serial is None:
            raise RuntimeError("Serial connection is closed.")

        deadline = time.time() + max(1.0, self.timeout_seconds) * 5
        while time.time() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue

            line = raw.decode("utf-8", errors="replace").strip()
            reading = parse_arduino_csv_line(line)
            if reading is not None:
                return reading

        raise TimeoutError(
            f"Timed out waiting for valid Arduino sensor data on {self.serial_port}"
        )

    def close(self) -> None:
        """Close serial connection."""

        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def __enter__(self) -> "BME688":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False
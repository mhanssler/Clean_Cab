"""Tests for Arduino serial BME688 parsing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bme688_driver import parse_arduino_csv_line


def test_parse_valid_arduino_csv_line():
    line = "1234,10,24.50,101325.00,42.10,51234.00,53000.00,0.96668,-3.33,LIVE,80"
    reading = parse_arduino_csv_line(line)

    assert reading is not None
    assert reading.temperature == 24.50
    assert reading.humidity == 42.10
    assert round(reading.pressure, 2) == 1013.25
    assert reading.gas_resistance == 51234.00


def test_parse_ignores_header_and_comments():
    assert parse_arduino_csv_line("# INFO: Connected to BME688") is None
    assert parse_arduino_csv_line(
        "host_ms,sample,temp_c,pressure_pa,humidity_pct,gas_ohm,baseline_ohm,gas_ratio,gas_delta_pct,phase,status_hex"
    ) is None


def test_parse_invalid_line_returns_none():
    assert parse_arduino_csv_line("garbage") is None
    assert parse_arduino_csv_line("1,2,3") is None

"""
Tests for DataLogger session metadata labeling.
"""

import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bme688_driver import SensorReading
from src.data_logger import DataLogger, LogConfig
from src.odor_classifier import OdorClass, OdorEvent, SeverityLevel


def test_session_metadata_attached_to_jsonl_records(tmp_path):
    session_metadata = {
        "session_id": "session_001",
        "session_mode": "odor_test",
        "test_type": "smoke",
        "expected_odor_class": "SMOKE",
        "session_label": "smoke_trial_1",
        "session_notes": "fan off, windows closed",
    }
    logger = DataLogger(
        LogConfig(
            log_directory=str(tmp_path),
            csv_enabled=False,
            json_enabled=True,
            flush_interval_seconds=0.01,
            buffer_size=1,
            session_metadata=session_metadata,
        )
    )

    logger.start()
    logger.log_reading(
        SensorReading(
            temperature=23.5,
            humidity=41.2,
            pressure=1012.8,
            gas_resistance=28750.0,
            timestamp=time.time(),
        )
    )
    logger.log_event(
        OdorEvent(
            odor_class=OdorClass.SMOKE,
            severity=SeverityLevel.MODERATE,
            confidence=0.83,
            gas_resistance=28750.0,
            timestamp=time.time(),
            temperature=23.5,
            humidity=41.2,
        )
    )
    logger.stop()

    jsonl_files = list(tmp_path.glob("readings_*.jsonl"))
    assert len(jsonl_files) == 1

    with open(jsonl_files[0], "r", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]

    assert len(records) >= 2
    for record in records:
        for key, value in session_metadata.items():
            assert record[key] == value


def test_session_columns_exist_in_csv_output(tmp_path):
    logger = DataLogger(
        LogConfig(
            log_directory=str(tmp_path),
            csv_enabled=True,
            json_enabled=False,
            flush_interval_seconds=0.01,
            buffer_size=1,
            session_metadata={
                "session_id": "session_002",
                "session_mode": "baseline",
                "test_type": "baseline_clean_air",
                "expected_odor_class": "CLEAN",
                "session_label": "baseline_trial",
                "session_notes": "",
            },
        )
    )

    logger.start()
    logger.log_reading(
        SensorReading(
            temperature=24.1,
            humidity=39.7,
            pressure=1013.4,
            gas_resistance=50200.0,
            timestamp=time.time(),
        )
    )
    logger.stop()

    csv_files = list(tmp_path.glob("readings_*.csv"))
    assert len(csv_files) == 1

    with open(csv_files[0], "r", encoding="utf-8") as handle:
        header = handle.readline().strip()

    assert "session_id" in header
    assert "session_mode" in header
    assert "test_type" in header
    assert "expected_odor_class" in header
    assert "session_label" in header
    assert "session_notes" in header

"""
Tests for BME688 driver simulation mode
"""

import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bme688_driver import SensorReading, HeaterProfile


class TestSensorReading:
    """Test SensorReading data structure."""
    
    def test_create_reading(self):
        reading = SensorReading(
            temperature=25.0,
            humidity=50.0,
            pressure=1013.25,
            gas_resistance=50000.0,
            timestamp=time.time()
        )
        
        assert reading.temperature == 25.0
        assert reading.humidity == 50.0
        assert reading.pressure == 1013.25
        assert reading.gas_resistance == 50000.0
    
    def test_reading_is_immutable(self):
        reading = SensorReading(25.0, 50.0, 1013.25, 50000.0, time.time())
        
        with pytest.raises(AttributeError):
            reading.temperature = 30.0


class TestHeaterProfile:
    """Test HeaterProfile configuration."""
    
    def test_default_values(self):
        profile = HeaterProfile()
        
        assert profile.temperature == 320
        assert profile.duration_ms == 150
    
    def test_custom_values(self):
        profile = HeaterProfile(temperature=350, duration_ms=200)
        
        assert profile.temperature == 350
        assert profile.duration_ms == 200

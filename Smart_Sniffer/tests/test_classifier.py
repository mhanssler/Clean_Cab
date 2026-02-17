"""
Tests for Odor Classifier
"""

import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.odor_classifier import (
    OdorClassifier, OdorClass, SeverityLevel, 
    OdorEvent, ClassifierConfig
)


class TestOdorClass:
    """Test OdorClass enumeration."""
    
    def test_all_classes_defined(self):
        expected_classes = [
            "CLEAN", "BODY_ODOR", "FLATULENCE", "BAD_BREATH",
            "FOOD_STRONG", "FOOD_FAST", "SMOKE", "ILLNESS", "UNKNOWN_FOUL"
        ]
        
        for name in expected_classes:
            assert hasattr(OdorClass, name)


class TestSeverityLevel:
    """Test SeverityLevel enumeration."""
    
    def test_severity_ordering(self):
        assert SeverityLevel.NONE.value < SeverityLevel.LOW.value
        assert SeverityLevel.LOW.value < SeverityLevel.MODERATE.value
        assert SeverityLevel.MODERATE.value < SeverityLevel.HIGH.value
        assert SeverityLevel.HIGH.value < SeverityLevel.SEVERE.value


class TestOdorClassifier:
    """Test OdorClassifier behavior."""
    
    def test_initialization(self):
        classifier = OdorClassifier()
        
        assert classifier.is_calibrating
        assert classifier.baseline_resistance is None
    
    def test_calibration_phase(self):
        classifier = OdorClassifier()
        
        # During calibration, should return CLEAN with 0 confidence
        for _ in range(30):
            event = classifier.process_reading(
                gas_resistance=50000,
                temperature=25.0,
                humidity=40.0
            )
        
        assert classifier.is_calibrating
        assert event.odor_class == OdorClass.CLEAN
    
    def test_baseline_establishment(self):
        classifier = OdorClassifier()
        
        # Feed consistent readings to establish baseline
        for _ in range(70):  # More than min_calibration_samples (60)
            classifier.process_reading(
                gas_resistance=50000,
                temperature=25.0,
                humidity=40.0
            )
        
        assert not classifier.is_calibrating
        assert classifier.baseline_resistance is not None
    
    def test_odor_detection(self):
        classifier = OdorClassifier()
        
        # Establish baseline
        for _ in range(70):
            classifier.process_reading(50000, 25.0, 40.0)
        
        # Simulate odor (30% of baseline resistance)
        event = classifier.process_reading(15000, 25.0, 40.0)
        
        assert event.severity != SeverityLevel.NONE
    
    def test_clean_air_after_calibration(self):
        classifier = OdorClassifier()
        
        # Establish baseline
        for _ in range(70):
            classifier.process_reading(50000, 25.0, 40.0)
        
        # Same resistance as baseline = clean air
        event = classifier.process_reading(50000, 25.0, 40.0)
        
        assert event.odor_class == OdorClass.CLEAN
        assert event.severity == SeverityLevel.NONE
    
    def test_reset_baseline(self):
        classifier = OdorClassifier()
        
        # Establish baseline
        for _ in range(70):
            classifier.process_reading(50000, 25.0, 40.0)
        
        assert not classifier.is_calibrating
        
        # Reset
        classifier.reset_baseline()
        
        assert classifier.is_calibrating
        assert classifier.baseline_resistance is None


class TestOdorEvent:
    """Test OdorEvent data structure."""
    
    def test_to_dict(self):
        event = OdorEvent(
            odor_class=OdorClass.BODY_ODOR,
            severity=SeverityLevel.MODERATE,
            confidence=0.85,
            gas_resistance=25000.0,
            timestamp=time.time(),
            temperature=25.0,
            humidity=45.0
        )
        
        d = event.to_dict()
        
        assert d["odor_class"] == "BODY_ODOR"
        assert d["severity"] == "MODERATE"
        assert d["confidence"] == 0.85

"""
Tests for Alert System
"""

import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.alerts import (
    AlertManager, AlertRule, Alert, AlertAction,
    console_handler, create_hvac_handler
)
from src.odor_classifier import OdorEvent, OdorClass, SeverityLevel


class TestAlertManager:
    """Test AlertManager functionality."""
    
    def test_initialization(self):
        manager = AlertManager()
        
        # Should have default rules
        assert len(manager._rules) > 0
    
    def test_add_rule(self):
        manager = AlertManager()
        
        rule = AlertRule(
            name="test_rule",
            odor_classes=[OdorClass.SMOKE],
            min_severity=SeverityLevel.LOW,
            actions=[AlertAction.LOG_ONLY]
        )
        
        manager.add_rule(rule)
        assert "test_rule" in manager._rules
    
    def test_remove_rule(self):
        manager = AlertManager()
        
        # Add and remove
        rule = AlertRule(
            name="temp_rule",
            odor_classes=[OdorClass.SMOKE],
            min_severity=SeverityLevel.LOW,
            actions=[AlertAction.LOG_ONLY]
        )
        manager.add_rule(rule)
        
        result = manager.remove_rule("temp_rule")
        
        assert result is True
        assert "temp_rule" not in manager._rules
    
    def test_clean_air_no_alert(self):
        manager = AlertManager()
        
        event = OdorEvent(
            odor_class=OdorClass.CLEAN,
            severity=SeverityLevel.NONE,
            confidence=1.0,
            gas_resistance=50000,
            timestamp=time.time(),
            temperature=25.0,
            humidity=45.0
        )
        
        alerts = manager.process_event(event)
        
        assert len(alerts) == 0
    
    def test_odor_generates_alert(self):
        manager = AlertManager()
        
        event = OdorEvent(
            odor_class=OdorClass.FLATULENCE,
            severity=SeverityLevel.MODERATE,
            confidence=0.8,
            gas_resistance=20000,
            timestamp=time.time(),
            temperature=25.0,
            humidity=45.0
        )
        
        alerts = manager.process_event(event)
        
        assert len(alerts) > 0
    
    def test_cooldown_prevents_duplicate_alerts(self):
        manager = AlertManager()
        
        event = OdorEvent(
            odor_class=OdorClass.SMOKE,
            severity=SeverityLevel.LOW,
            confidence=0.7,
            gas_resistance=35000,
            timestamp=time.time(),
            temperature=25.0,
            humidity=45.0
        )
        
        # First event generates alert
        alerts1 = manager.process_event(event)
        
        # Immediate second event should be blocked by cooldown
        alerts2 = manager.process_event(event)
        
        assert len(alerts1) > 0
        assert len(alerts2) == 0  # Blocked by cooldown


class TestHVACHandler:
    """Test HVAC handler creation."""
    
    def test_create_hvac_handler(self):
        received_levels = []
        
        def callback(level):
            received_levels.append(level)
        
        handler = create_hvac_handler(callback)
        
        event = OdorEvent(
            odor_class=OdorClass.FLATULENCE,
            severity=SeverityLevel.HIGH,
            confidence=0.9,
            gas_resistance=15000,
            timestamp=time.time(),
            temperature=25.0,
            humidity=45.0
        )
        
        alert = Alert(
            rule_name="test",
            event=event,
            actions=[AlertAction.ACTIVATE_HVAC],
            message="Test alert",
            priority=3
        )
        
        handler(alert)
        
        assert len(received_levels) == 1
        assert received_levels[0] == 100  # HIGH severity = 100%

"""
Alert System for AV Cabin Air Quality
Generates alerts based on odor classification results.
Supports multiple notification channels for AV integration.
"""

import time
import json
import logging
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any
from collections import deque

from .odor_classifier import OdorEvent, OdorClass, SeverityLevel


class AlertAction(Enum):
    """Actions that can be triggered by alerts."""
    LOG_ONLY = auto()           # Just log the event
    NOTIFY_DISPLAY = auto()     # Show on AV display
    NOTIFY_SOUND = auto()       # Audio notification
    ACTIVATE_HVAC = auto()      # Trigger HVAC/ventilation
    NOTIFY_FLEET = auto()       # Send to fleet management
    EMERGENCY_STOP = auto()     # Severe - request stop (e.g., illness)


@dataclass
class AlertRule:
    """Defines when and how to generate alerts."""
    name: str
    odor_classes: List[OdorClass]           # Which odors trigger this rule
    min_severity: SeverityLevel             # Minimum severity to trigger
    actions: List[AlertAction]               # Actions to take
    cooldown_seconds: float = 30.0           # Minimum time between alerts
    message_template: str = ""               # Alert message template
    priority: int = 1                        # Higher = more urgent
    
    def __post_init__(self):
        if not self.message_template:
            self.message_template = (
                "Air quality alert: {odor_class} detected "
                "(severity: {severity})"
            )


@dataclass
class Alert:
    """Generated alert."""
    rule_name: str
    event: OdorEvent
    actions: List[AlertAction]
    message: str
    priority: int
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    
    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "event": self.event.to_dict(),
            "actions": [a.name for a in self.actions],
            "message": self.message,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "acknowledged": self.acknowledged
        }


class AlertManager:
    """
    Manages alert generation and dispatch for AV air quality system.
    """
    
    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._last_alert_time: Dict[str, float] = {}
        self._alert_history: deque = deque(maxlen=1000)
        self._handlers: Dict[AlertAction, List[Callable]] = {
            action: [] for action in AlertAction
        }
        self._active_alerts: List[Alert] = []
        
        # Set up logging
        self._logger = logging.getLogger("SmartSniffer.Alerts")
        
        # Register default rules
        self._register_default_rules()
    
    def _register_default_rules(self) -> None:
        """Register default alert rules for AV cabin monitoring."""
        
        # Mild odor - just ventilate
        self.add_rule(AlertRule(
            name="mild_odor",
            odor_classes=[
                OdorClass.BODY_ODOR, 
                OdorClass.FOOD_STRONG,
                OdorClass.FOOD_FAST
            ],
            min_severity=SeverityLevel.LOW,
            actions=[AlertAction.LOG_ONLY, AlertAction.ACTIVATE_HVAC],
            cooldown_seconds=60.0,
            message_template="Mild air quality issue detected. Increasing ventilation.",
            priority=1
        ))
        
        # Moderate odor - notify and ventilate
        self.add_rule(AlertRule(
            name="moderate_odor",
            odor_classes=[
                OdorClass.BODY_ODOR,
                OdorClass.FLATULENCE,
                OdorClass.BAD_BREATH,
                OdorClass.FOOD_STRONG,
                OdorClass.SMOKE
            ],
            min_severity=SeverityLevel.MODERATE,
            actions=[
                AlertAction.LOG_ONLY, 
                AlertAction.NOTIFY_DISPLAY,
                AlertAction.ACTIVATE_HVAC
            ],
            cooldown_seconds=30.0,
            message_template=(
                "Air quality notice: {odor_class} detected. "
                "Fresh air circulation activated."
            ),
            priority=2
        ))
        
        # High severity - strong notification
        self.add_rule(AlertRule(
            name="high_odor",
            odor_classes=list(OdorClass),  # All odor types
            min_severity=SeverityLevel.HIGH,
            actions=[
                AlertAction.LOG_ONLY,
                AlertAction.NOTIFY_DISPLAY,
                AlertAction.NOTIFY_SOUND,
                AlertAction.ACTIVATE_HVAC,
                AlertAction.NOTIFY_FLEET
            ],
            cooldown_seconds=15.0,
            message_template=(
                "⚠️ Air quality warning: Strong {odor_class} detected. "
                "Maximum ventilation engaged."
            ),
            priority=3
        ))
        
        # Illness detection - potential emergency
        self.add_rule(AlertRule(
            name="illness_detected",
            odor_classes=[OdorClass.ILLNESS],
            min_severity=SeverityLevel.MODERATE,
            actions=[
                AlertAction.LOG_ONLY,
                AlertAction.NOTIFY_DISPLAY,
                AlertAction.NOTIFY_SOUND,
                AlertAction.NOTIFY_FLEET,
                AlertAction.EMERGENCY_STOP
            ],
            cooldown_seconds=10.0,
            message_template=(
                "🚨 HEALTH ALERT: Possible passenger illness detected. "
                "Initiating safety protocol."
            ),
            priority=5
        ))
        
        # Smoke detection
        self.add_rule(AlertRule(
            name="smoke_detected",
            odor_classes=[OdorClass.SMOKE],
            min_severity=SeverityLevel.LOW,
            actions=[
                AlertAction.LOG_ONLY,
                AlertAction.NOTIFY_DISPLAY,
                AlertAction.NOTIFY_SOUND,
                AlertAction.ACTIVATE_HVAC
            ],
            cooldown_seconds=30.0,
            message_template=(
                "🚭 Smoke residue detected. This is a smoke-free vehicle. "
                "Air filtration activated."
            ),
            priority=3
        ))
    
    def add_rule(self, rule: AlertRule) -> None:
        """Add or update an alert rule."""
        self._rules[rule.name] = rule
        self._last_alert_time[rule.name] = 0
    
    def remove_rule(self, name: str) -> bool:
        """Remove an alert rule."""
        if name in self._rules:
            del self._rules[name]
            return True
        return False
    
    def register_handler(
        self, 
        action: AlertAction, 
        handler: Callable[[Alert], None]
    ) -> None:
        """Register a handler function for an alert action."""
        self._handlers[action].append(handler)
    
    def process_event(self, event: OdorEvent) -> List[Alert]:
        """
        Process an odor event and generate any applicable alerts.
        
        Args:
            event: OdorEvent from classifier
            
        Returns:
            List of generated alerts
        """
        generated_alerts = []
        current_time = time.time()
        
        # Check each rule
        for rule in sorted(
            self._rules.values(), 
            key=lambda r: r.priority, 
            reverse=True
        ):
            # Check if odor class matches
            if event.odor_class not in rule.odor_classes:
                continue
            
            # Check severity threshold
            if event.severity.value < rule.min_severity.value:
                continue
            
            # Check cooldown
            last_time = self._last_alert_time.get(rule.name, 0)
            if current_time - last_time < rule.cooldown_seconds:
                continue
            
            # Generate alert
            message = rule.message_template.format(
                odor_class=event.odor_class.name.replace('_', ' ').title(),
                severity=event.severity.name.lower(),
                confidence=f"{event.confidence*100:.0f}%",
                temperature=f"{event.temperature:.1f}°C",
                humidity=f"{event.humidity:.1f}%"
            )
            
            alert = Alert(
                rule_name=rule.name,
                event=event,
                actions=rule.actions,
                message=message,
                priority=rule.priority
            )
            
            # Update last alert time
            self._last_alert_time[rule.name] = current_time
            
            # Store alert
            self._alert_history.append(alert)
            self._active_alerts.append(alert)
            generated_alerts.append(alert)
            
            # Dispatch to handlers
            self._dispatch_alert(alert)
            
            # Log alert
            self._logger.info(
                f"Alert generated: {rule.name} - {message}"
            )
        
        return generated_alerts
    
    def _dispatch_alert(self, alert: Alert) -> None:
        """Dispatch alert to registered handlers."""
        for action in alert.actions:
            for handler in self._handlers[action]:
                try:
                    handler(alert)
                except Exception as e:
                    self._logger.error(
                        f"Error in alert handler for {action.name}: {e}"
                    )
    
    def acknowledge_alert(self, alert: Alert) -> None:
        """Mark an alert as acknowledged."""
        alert.acknowledged = True
        if alert in self._active_alerts:
            self._active_alerts.remove(alert)
    
    def acknowledge_all(self) -> int:
        """Acknowledge all active alerts. Returns count acknowledged."""
        count = len(self._active_alerts)
        for alert in self._active_alerts:
            alert.acknowledged = True
        self._active_alerts.clear()
        return count
    
    def get_active_alerts(self) -> List[Alert]:
        """Get list of unacknowledged alerts."""
        return list(self._active_alerts)
    
    def get_alert_history(self, count: int = 50) -> List[Alert]:
        """Get recent alert history."""
        return list(self._alert_history)[-count:]
    
    def get_statistics(self) -> dict:
        """Get alert statistics."""
        # Count by rule
        rule_counts = {}
        for alert in self._alert_history:
            rule_counts[alert.rule_name] = rule_counts.get(alert.rule_name, 0) + 1
        
        # Count by severity
        severity_counts = {}
        for alert in self._alert_history:
            sev = alert.event.severity.name
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        return {
            "total_alerts": len(self._alert_history),
            "active_alerts": len(self._active_alerts),
            "rules_count": len(self._rules),
            "alerts_by_rule": rule_counts,
            "alerts_by_severity": severity_counts
        }


# Default handlers for common actions
def log_handler(alert: Alert) -> None:
    """Default logging handler."""
    logging.info(f"[ALERT] {alert.message}")


def console_handler(alert: Alert) -> None:
    """Print alert to console."""
    severity_emoji = {
        SeverityLevel.LOW: "ℹ️",
        SeverityLevel.MODERATE: "⚠️",
        SeverityLevel.HIGH: "🔶",
        SeverityLevel.SEVERE: "🚨"
    }
    emoji = severity_emoji.get(alert.event.severity, "📢")
    print(f"{emoji} {alert.message}")


def create_hvac_handler(
    callback: Callable[[int], None]
) -> Callable[[Alert], None]:
    """
    Create HVAC handler that calls callback with ventilation level.
    
    Args:
        callback: Function that accepts ventilation level (0-100)
    """
    def handler(alert: Alert) -> None:
        # Map severity to ventilation level
        levels = {
            SeverityLevel.LOW: 50,
            SeverityLevel.MODERATE: 75,
            SeverityLevel.HIGH: 100,
            SeverityLevel.SEVERE: 100
        }
        level = levels.get(alert.event.severity, 50)
        callback(level)
    
    return handler

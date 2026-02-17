"""
Odor Classification for AV Cabin Air Quality
Classifies foul odors commonly encountered in autonomous vehicle environments.

Target odor classes for human co-habitation:
- Clean air (baseline)
- Body odor (perspiration)
- Flatulence
- Bad breath
- Food odors (strong foods, fast food)
- Smoke residue
- Illness indicators (vomit)
"""

import time
import json
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque
import math


class OdorClass(Enum):
    """Classification of detected odors in AV cabin."""
    CLEAN = auto()           # Normal/fresh air
    BODY_ODOR = auto()       # Perspiration, sweat
    FLATULENCE = auto()      # Intestinal gas
    BAD_BREATH = auto()      # Halitosis
    FOOD_STRONG = auto()     # Strong food (garlic, onion, fish)
    FOOD_FAST = auto()       # Fast food, fried foods
    SMOKE = auto()           # Cigarette/vape residue
    ILLNESS = auto()         # Vomit, sickness
    UNKNOWN_FOUL = auto()    # Unclassified foul odor


class SeverityLevel(Enum):
    """Severity level of detected odor."""
    NONE = 0
    LOW = 1
    MODERATE = 2
    HIGH = 3
    SEVERE = 4


@dataclass
class OdorEvent:
    """Represents a detected odor event."""
    odor_class: OdorClass
    severity: SeverityLevel
    confidence: float           # 0.0 to 1.0
    gas_resistance: float       # Ohms
    timestamp: float
    temperature: float
    humidity: float
    
    def to_dict(self) -> dict:
        return {
            "odor_class": self.odor_class.name,
            "severity": self.severity.name,
            "confidence": round(self.confidence, 3),
            "gas_resistance": round(self.gas_resistance, 2),
            "timestamp": self.timestamp,
            "temperature": round(self.temperature, 2),
            "humidity": round(self.humidity, 2)
        }


@dataclass
class ClassifierConfig:
    """Configuration for odor classifier."""
    # Baseline tracking
    baseline_window_size: int = 300     # 5 minutes at 1Hz
    baseline_percentile: float = 0.9    # Use 90th percentile as baseline
    
    # Detection thresholds (ratio of current to baseline)
    threshold_low: float = 0.7          # 30% drop in resistance
    threshold_moderate: float = 0.5     # 50% drop
    threshold_high: float = 0.3         # 70% drop
    threshold_severe: float = 0.15      # 85% drop
    
    # Temperature compensation
    temp_reference: float = 25.0        # Reference temperature (°C)
    temp_coefficient: float = 0.02      # 2% per degree
    
    # Humidity compensation  
    humidity_reference: float = 40.0    # Reference humidity (%RH)
    humidity_coefficient: float = 0.01  # 1% per %RH
    
    # Smoothing
    smoothing_window: int = 5           # 5-sample moving average
    
    # Classification patterns (resistance change profiles)
    # These would ideally be trained via BME AI-Studio
    odor_profiles: Dict[str, Dict] = field(default_factory=dict)
    
    def __post_init__(self):
        # Default odor profiles based on typical VOC characteristics
        # In production, these would be trained with BME AI-Studio
        if not self.odor_profiles:
            self.odor_profiles = {
                OdorClass.BODY_ODOR.name: {
                    "resistance_drop_min": 0.3,
                    "resistance_drop_max": 0.7,
                    "onset_rate": "gradual",     # Slow onset
                    "decay_rate": "slow",        # Persists
                },
                OdorClass.FLATULENCE.name: {
                    "resistance_drop_min": 0.2,
                    "resistance_drop_max": 0.6,
                    "onset_rate": "rapid",       # Sudden
                    "decay_rate": "moderate",    # Dissipates
                },
                OdorClass.BAD_BREATH.name: {
                    "resistance_drop_min": 0.5,
                    "resistance_drop_max": 0.8,
                    "onset_rate": "moderate",
                    "decay_rate": "moderate",
                },
                OdorClass.FOOD_STRONG.name: {
                    "resistance_drop_min": 0.2,
                    "resistance_drop_max": 0.5,
                    "onset_rate": "gradual",
                    "decay_rate": "very_slow",   # Lingers
                },
                OdorClass.FOOD_FAST.name: {
                    "resistance_drop_min": 0.3,
                    "resistance_drop_max": 0.6,
                    "onset_rate": "moderate",
                    "decay_rate": "slow",
                },
                OdorClass.SMOKE.name: {
                    "resistance_drop_min": 0.1,
                    "resistance_drop_max": 0.4,
                    "onset_rate": "gradual",
                    "decay_rate": "very_slow",
                },
                OdorClass.ILLNESS.name: {
                    "resistance_drop_min": 0.05,
                    "resistance_drop_max": 0.3,
                    "onset_rate": "rapid",
                    "decay_rate": "slow",
                },
            }


class OdorClassifier:
    """
    Classifies odors in autonomous vehicle cabin environment.
    
    Uses gas resistance changes from BME688 to detect and classify
    foul odors that may occur during human occupancy.
    """
    
    def __init__(self, config: Optional[ClassifierConfig] = None):
        self.config = config or ClassifierConfig()
        
        # Baseline tracking (high resistance = clean air)
        self._baseline_buffer: deque = deque(maxlen=self.config.baseline_window_size)
        self._baseline_resistance: Optional[float] = None
        
        # Smoothing buffer
        self._smoothing_buffer: deque = deque(maxlen=self.config.smoothing_window)
        
        # Rate of change tracking
        self._prev_resistance: Optional[float] = None
        self._prev_timestamp: Optional[float] = None
        self._rate_history: deque = deque(maxlen=10)
        
        # Event history
        self._recent_events: deque = deque(maxlen=100)
        
        # State
        self._is_calibrating = True
        self._calibration_samples = 0
        self._min_calibration_samples = 60  # 1 minute warmup
    
    def process_reading(
        self, 
        gas_resistance: float,
        temperature: float,
        humidity: float,
        timestamp: Optional[float] = None
    ) -> OdorEvent:
        """
        Process a sensor reading and classify any detected odor.
        
        Args:
            gas_resistance: Gas resistance in Ohms
            temperature: Temperature in Celsius
            humidity: Relative humidity in %RH
            timestamp: Unix timestamp (defaults to current time)
            
        Returns:
            OdorEvent with classification results
        """
        timestamp = timestamp or time.time()
        
        # Apply environmental compensation
        compensated_resistance = self._compensate_reading(
            gas_resistance, temperature, humidity
        )
        
        # Update smoothing buffer
        self._smoothing_buffer.append(compensated_resistance)
        smoothed_resistance = self._get_smoothed_value()
        
        # Update rate of change
        onset_rate = self._update_rate_tracking(smoothed_resistance, timestamp)
        
        # Update baseline
        self._update_baseline(smoothed_resistance)
        
        # Check calibration status
        if self._is_calibrating:
            self._calibration_samples += 1
            if self._calibration_samples >= self._min_calibration_samples:
                self._is_calibrating = False
            
            return OdorEvent(
                odor_class=OdorClass.CLEAN,
                severity=SeverityLevel.NONE,
                confidence=0.0,
                gas_resistance=gas_resistance,
                timestamp=timestamp,
                temperature=temperature,
                humidity=humidity
            )
        
        # Classify odor
        odor_class, severity, confidence = self._classify(
            smoothed_resistance, onset_rate
        )
        
        event = OdorEvent(
            odor_class=odor_class,
            severity=severity,
            confidence=confidence,
            gas_resistance=gas_resistance,
            timestamp=timestamp,
            temperature=temperature,
            humidity=humidity
        )
        
        # Store event if significant
        if severity != SeverityLevel.NONE:
            self._recent_events.append(event)
        
        return event
    
    def _compensate_reading(
        self, 
        resistance: float, 
        temperature: float, 
        humidity: float
    ) -> float:
        """Apply temperature and humidity compensation."""
        # Temperature compensation
        temp_factor = 1.0 + (
            self.config.temp_coefficient * 
            (temperature - self.config.temp_reference)
        )
        
        # Humidity compensation
        humidity_factor = 1.0 + (
            self.config.humidity_coefficient * 
            (humidity - self.config.humidity_reference)
        )
        
        return resistance * temp_factor * humidity_factor
    
    def _get_smoothed_value(self) -> float:
        """Get smoothed resistance value."""
        if not self._smoothing_buffer:
            return 0.0
        return sum(self._smoothing_buffer) / len(self._smoothing_buffer)
    
    def _update_rate_tracking(
        self, 
        resistance: float, 
        timestamp: float
    ) -> str:
        """Track rate of resistance change."""
        if self._prev_resistance is None:
            self._prev_resistance = resistance
            self._prev_timestamp = timestamp
            return "stable"
        
        dt = timestamp - self._prev_timestamp
        if dt > 0:
            # Rate of change as percentage per second
            rate = (resistance - self._prev_resistance) / (self._prev_resistance * dt)
            self._rate_history.append(rate)
        
        self._prev_resistance = resistance
        self._prev_timestamp = timestamp
        
        # Classify onset rate
        if not self._rate_history:
            return "stable"
        
        avg_rate = sum(self._rate_history) / len(self._rate_history)
        
        if avg_rate < -0.1:
            return "rapid"      # Fast decrease (odor onset)
        elif avg_rate < -0.02:
            return "moderate"
        elif avg_rate < -0.005:
            return "gradual"
        elif avg_rate > 0.02:
            return "recovery"   # Air clearing
        else:
            return "stable"
    
    def _update_baseline(self, resistance: float) -> None:
        """Update baseline resistance for clean air."""
        self._baseline_buffer.append(resistance)
        
        if len(self._baseline_buffer) >= 10:
            # Use high percentile as baseline (assumes mostly clean air)
            sorted_values = sorted(self._baseline_buffer)
            idx = int(len(sorted_values) * self.config.baseline_percentile)
            self._baseline_resistance = sorted_values[min(idx, len(sorted_values)-1)]
    
    def _classify(
        self, 
        resistance: float, 
        onset_rate: str
    ) -> Tuple[OdorClass, SeverityLevel, float]:
        """Classify odor based on resistance and rate of change."""
        if self._baseline_resistance is None:
            return OdorClass.CLEAN, SeverityLevel.NONE, 0.0
        
        # Calculate resistance ratio (lower = more VOCs detected)
        ratio = resistance / self._baseline_resistance
        
        # Determine severity based on resistance drop
        if ratio > self.config.threshold_low:
            severity = SeverityLevel.NONE
        elif ratio > self.config.threshold_moderate:
            severity = SeverityLevel.LOW
        elif ratio > self.config.threshold_high:
            severity = SeverityLevel.MODERATE
        elif ratio > self.config.threshold_severe:
            severity = SeverityLevel.HIGH
        else:
            severity = SeverityLevel.SEVERE
        
        if severity == SeverityLevel.NONE:
            return OdorClass.CLEAN, severity, 1.0
        
        # Classify odor type based on pattern matching
        odor_class, confidence = self._match_odor_pattern(ratio, onset_rate)
        
        return odor_class, severity, confidence
    
    def _match_odor_pattern(
        self, 
        ratio: float, 
        onset_rate: str
    ) -> Tuple[OdorClass, float]:
        """Match current reading to known odor profiles."""
        best_match = OdorClass.UNKNOWN_FOUL
        best_confidence = 0.3  # Default confidence for unknown
        
        drop = 1.0 - ratio  # Convert ratio to drop percentage
        
        for odor_name, profile in self.config.odor_profiles.items():
            try:
                odor_class = OdorClass[odor_name]
            except KeyError:
                continue
            
            # Check if drop is within expected range
            if profile["resistance_drop_min"] <= drop <= profile["resistance_drop_max"]:
                # Check onset rate match
                rate_match = (onset_rate == profile["onset_rate"])
                
                # Calculate confidence
                range_center = (
                    profile["resistance_drop_min"] + 
                    profile["resistance_drop_max"]
                ) / 2
                range_width = (
                    profile["resistance_drop_max"] - 
                    profile["resistance_drop_min"]
                )
                
                # Higher confidence when closer to center of expected range
                distance = abs(drop - range_center) / (range_width / 2)
                base_confidence = max(0.4, 1.0 - distance * 0.5)
                
                # Boost confidence if onset rate matches
                if rate_match:
                    base_confidence = min(0.95, base_confidence + 0.2)
                
                if base_confidence > best_confidence:
                    best_confidence = base_confidence
                    best_match = odor_class
        
        return best_match, best_confidence
    
    @property
    def is_calibrating(self) -> bool:
        """Check if classifier is still in calibration phase."""
        return self._is_calibrating
    
    @property
    def baseline_resistance(self) -> Optional[float]:
        """Get current baseline resistance value."""
        return self._baseline_resistance
    
    def get_recent_events(self, count: int = 10) -> List[OdorEvent]:
        """Get most recent odor events."""
        return list(self._recent_events)[-count:]
    
    def get_statistics(self) -> dict:
        """Get classifier statistics."""
        return {
            "is_calibrating": self._is_calibrating,
            "baseline_resistance": self._baseline_resistance,
            "samples_collected": len(self._baseline_buffer),
            "recent_events_count": len(self._recent_events),
            "calibration_progress": min(
                1.0, 
                self._calibration_samples / self._min_calibration_samples
            )
        }
    
    def reset_baseline(self) -> None:
        """Reset baseline calibration."""
        self._baseline_buffer.clear()
        self._baseline_resistance = None
        self._is_calibrating = True
        self._calibration_samples = 0
    
    def save_config(self, filepath: str) -> None:
        """Save classifier configuration to file."""
        config_dict = {
            "baseline_window_size": self.config.baseline_window_size,
            "baseline_percentile": self.config.baseline_percentile,
            "threshold_low": self.config.threshold_low,
            "threshold_moderate": self.config.threshold_moderate,
            "threshold_high": self.config.threshold_high,
            "threshold_severe": self.config.threshold_severe,
            "temp_reference": self.config.temp_reference,
            "temp_coefficient": self.config.temp_coefficient,
            "humidity_reference": self.config.humidity_reference,
            "humidity_coefficient": self.config.humidity_coefficient,
            "odor_profiles": self.config.odor_profiles
        }
        
        with open(filepath, 'w') as f:
            json.dump(config_dict, f, indent=2)
    
    @classmethod
    def load_config(cls, filepath: str) -> 'OdorClassifier':
        """Load classifier from configuration file."""
        with open(filepath, 'r') as f:
            config_dict = json.load(f)
        
        config = ClassifierConfig(**config_dict)
        return cls(config)

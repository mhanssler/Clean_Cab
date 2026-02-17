"""
Smart Sniffer - AV Cabin Air Quality Monitor
Main application for BME688-based foul odor detection in autonomous vehicles.

Features:
- 1Hz periodic sampling of cabin air
- Real-time odor classification
- Alert generation for HVAC and fleet management integration
- Data logging for analysis and model training
"""

import os
import sys
import time
import signal
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bme688_driver import BME688, SensorReading
from src.odor_classifier import OdorClassifier, OdorEvent, OdorClass, SeverityLevel
from src.alerts import AlertManager, AlertAction, console_handler, create_hvac_handler
from src.data_logger import DataLogger, LogConfig


# Configuration defaults
DEFAULT_CONFIG = {
    "sensor": {
        "i2c_bus": 1,
        "i2c_address": 0x76,
        "heater_temp": 320,
        "heater_duration_ms": 150
    },
    "sampling": {
        "interval_seconds": 1.0,
        "warmup_seconds": 60
    },
    "logging": {
        "directory": "logs",
        "level": "INFO",
        "csv_enabled": True,
        "json_enabled": True
    },
    "alerts": {
        "console_enabled": True,
        "hvac_enabled": True
    }
}


class SmartSniffer:
    """
    Main application class for AV Cabin Air Quality monitoring.
    """
    
    def __init__(self, config: Optional[dict] = None, simulate: bool = False):
        """
        Initialize Smart Sniffer.
        
        Args:
            config: Configuration dictionary
            simulate: If True, use simulated sensor data (for testing)
        """
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.simulate = simulate
        
        # Set up logging
        self._setup_logging()
        self.logger = logging.getLogger("SmartSniffer")
        
        # Components
        self.sensor: Optional[BME688] = None
        self.classifier: Optional[OdorClassifier] = None
        self.alert_manager: Optional[AlertManager] = None
        self.data_logger: Optional[DataLogger] = None
        
        # State
        self._running = False
        self._sample_count = 0
        self._start_time: Optional[float] = None
        
        # Statistics
        self._stats = {
            "samples_total": 0,
            "samples_with_odor": 0,
            "alerts_generated": 0,
            "errors": 0
        }
    
    def _setup_logging(self) -> None:
        """Configure application logging."""
        log_level = getattr(
            logging, 
            self.config["logging"]["level"].upper(), 
            logging.INFO
        )
        
        # Create logs directory
        log_dir = Path(self.config["logging"]["directory"])
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Configure logging
        log_file = log_dir / f"smart_sniffer_{datetime.now():%Y%m%d}.log"
        
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    def initialize(self) -> bool:
        """
        Initialize all components.
        
        Returns:
            True if initialization successful
        """
        self.logger.info("Initializing Smart Sniffer...")
        
        try:
            # Initialize sensor (only if not simulating)
            if not self.simulate:
                try:
                    from src.bme688_driver import _SMBUS_AVAILABLE
                    if not _SMBUS_AVAILABLE:
                        self.logger.warning(
                            "I2C library not available - falling back to simulation mode"
                        )
                        self.simulate = True
                    else:
                        self.logger.info("Connecting to BME688 sensor...")
                        self.sensor = BME688(
                            i2c_bus=self.config["sensor"]["i2c_bus"],
                            address=self.config["sensor"]["i2c_address"]
                        )
                        self.sensor.set_heater_profile(
                            temperature=self.config["sensor"]["heater_temp"],
                            duration_ms=self.config["sensor"]["heater_duration_ms"]
                        )
                        self.logger.info("BME688 sensor connected successfully")
                except Exception as e:
                    self.logger.warning(f"Sensor init failed: {e} - using simulation")
                    self.simulate = True
            
            if self.simulate:
                self.logger.info("Running in simulation mode")
            
            # Initialize classifier
            self.classifier = OdorClassifier()
            self.logger.info("Odor classifier initialized")
            
            # Initialize alert manager
            self.alert_manager = AlertManager()
            
            # Register alert handlers
            if self.config["alerts"]["console_enabled"]:
                self.alert_manager.register_handler(
                    AlertAction.NOTIFY_DISPLAY, 
                    console_handler
                )
                self.alert_manager.register_handler(
                    AlertAction.NOTIFY_SOUND, 
                    console_handler
                )
            
            if self.config["alerts"]["hvac_enabled"]:
                self.alert_manager.register_handler(
                    AlertAction.ACTIVATE_HVAC,
                    create_hvac_handler(self._hvac_callback)
                )
            
            self.logger.info("Alert manager initialized")
            
            # Initialize data logger
            log_config = LogConfig(
                log_directory=self.config["logging"]["directory"],
                csv_enabled=self.config["logging"]["csv_enabled"],
                json_enabled=self.config["logging"]["json_enabled"]
            )
            self.data_logger = DataLogger(log_config)
            self.data_logger.start()
            self.logger.info("Data logger started")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Initialization failed: {e}")
            return False
    
    def _hvac_callback(self, level: int) -> None:
        """Callback for HVAC control (placeholder for AV integration)."""
        self.logger.info(f"HVAC ventilation request: {level}%")
        # In real implementation, this would interface with AV HVAC system
    
    def _read_sensor(self) -> SensorReading:
        """Read from sensor or generate simulated data."""
        if self.simulate:
            return self._simulate_reading()
        return self.sensor.read()
    
    def _simulate_reading(self) -> SensorReading:
        """Generate simulated sensor readings for testing."""
        import random
        
        base_resistance = 50000  # Base resistance in clean air
        
        # Occasionally simulate odor events
        if random.random() < 0.05:  # 5% chance of odor
            # Simulate resistance drop (odor detection)
            resistance_factor = random.uniform(0.2, 0.8)
        else:
            # Normal variation
            resistance_factor = random.uniform(0.9, 1.1)
        
        return SensorReading(
            temperature=22.0 + random.uniform(-2, 2),
            humidity=45.0 + random.uniform(-10, 10),
            pressure=1013.25 + random.uniform(-5, 5),
            gas_resistance=base_resistance * resistance_factor,
            timestamp=time.time()
        )
    
    def run(self) -> None:
        """Main sampling loop."""
        if not self.initialize():
            self.logger.error("Failed to initialize. Exiting.")
            return
        
        self._running = True
        self._start_time = time.time()
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        interval = self.config["sampling"]["interval_seconds"]
        warmup = self.config["sampling"]["warmup_seconds"]
        
        self.logger.info(
            f"Starting air quality monitoring (interval: {interval}s, "
            f"warmup: {warmup}s)"
        )
        
        print("\n" + "="*60)
        print("  SMART SNIFFER - AV Cabin Air Quality Monitor")
        print("="*60)
        print(f"  Sampling Rate: {1/interval:.1f} Hz")
        print(f"  Warmup Period: {warmup} seconds")
        print(f"  Mode: {'Simulation' if self.simulate else 'Live Sensor'}")
        print("="*60 + "\n")
        
        try:
            while self._running:
                cycle_start = time.time()
                
                try:
                    # Read sensor
                    reading = self._read_sensor()
                    self._sample_count += 1
                    self._stats["samples_total"] += 1
                    
                    # Log raw reading
                    self.data_logger.log_reading(reading)
                    
                    # Classify odor
                    event = self.classifier.process_reading(
                        gas_resistance=reading.gas_resistance,
                        temperature=reading.temperature,
                        humidity=reading.humidity,
                        timestamp=reading.timestamp
                    )
                    
                    # Log classification event
                    if event.severity != SeverityLevel.NONE:
                        self.data_logger.log_event(event)
                        self._stats["samples_with_odor"] += 1
                    
                    # Process alerts
                    alerts = self.alert_manager.process_event(event)
                    self._stats["alerts_generated"] += len(alerts)
                    
                    # Display status
                    self._display_status(reading, event)
                    
                except Exception as e:
                    self.logger.error(f"Error in sampling loop: {e}")
                    self._stats["errors"] += 1
                
                # Maintain sampling interval
                elapsed = time.time() - cycle_start
                sleep_time = max(0, interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
        finally:
            self.shutdown()
    
    def _display_status(self, reading: SensorReading, event: OdorEvent) -> None:
        """Display current status to console."""
        runtime = time.time() - self._start_time
        
        # Status line
        status_parts = [
            f"T:{reading.temperature:5.1f}°C",
            f"H:{reading.humidity:5.1f}%",
            f"P:{reading.pressure:7.1f}hPa",
            f"Gas:{reading.gas_resistance:8.0f}Ω"
        ]
        
        # Classifier status
        if self.classifier.is_calibrating:
            progress = self.classifier.get_statistics()["calibration_progress"]
            status_parts.append(f"[Calibrating {progress*100:.0f}%]")
        else:
            odor_str = event.odor_class.name.replace('_', ' ')
            if event.severity != SeverityLevel.NONE:
                status_parts.append(f"[{odor_str}: {event.severity.name}]")
            else:
                status_parts.append("[Air: OK]")
        
        # Print status line (overwrite previous)
        status_line = " | ".join(status_parts)
        print(f"\r[{runtime:6.0f}s] {status_line}", end="", flush=True)
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self._running = False
    
    def shutdown(self) -> None:
        """Clean shutdown of all components."""
        self.logger.info("Shutting down Smart Sniffer...")
        
        print("\n")  # New line after status display
        
        # Stop data logger
        if self.data_logger:
            self.data_logger.stop()
            self.logger.info("Data logger stopped")
        
        # Close sensor
        if self.sensor:
            self.sensor.close()
            self.logger.info("Sensor connection closed")
        
        # Print summary
        self._print_summary()
    
    def _print_summary(self) -> None:
        """Print session summary."""
        if self._start_time:
            runtime = time.time() - self._start_time
        else:
            runtime = 0
        
        print("\n" + "="*60)
        print("  SESSION SUMMARY")
        print("="*60)
        print(f"  Runtime: {runtime:.1f} seconds")
        print(f"  Total Samples: {self._stats['samples_total']}")
        print(f"  Odor Detections: {self._stats['samples_with_odor']}")
        print(f"  Alerts Generated: {self._stats['alerts_generated']}")
        print(f"  Errors: {self._stats['errors']}")
        
        if self.classifier:
            stats = self.classifier.get_statistics()
            print(f"  Baseline Resistance: {stats['baseline_resistance']:.0f}Ω" 
                  if stats['baseline_resistance'] else "  Baseline: Not established")
        
        print("="*60 + "\n")
    
    def get_status(self) -> dict:
        """Get current system status."""
        return {
            "running": self._running,
            "mode": "simulation" if self.simulate else "live",
            "sample_count": self._sample_count,
            "runtime": time.time() - self._start_time if self._start_time else 0,
            "stats": self._stats,
            "classifier": self.classifier.get_statistics() if self.classifier else None,
            "alerts": self.alert_manager.get_statistics() if self.alert_manager else None,
            "logging": self.data_logger.get_statistics() if self.data_logger else None
        }


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Smart Sniffer - AV Cabin Air Quality Monitor"
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to configuration file (JSON)"
    )
    parser.add_argument(
        "-s", "--simulate",
        action="store_true",
        help="Run in simulation mode (no sensor required)"
    )
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=1.0,
        help="Sampling interval in seconds (default: 1.0)"
    )
    parser.add_argument(
        "-l", "--log-dir",
        default="logs",
        help="Log directory (default: logs)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Build configuration
    config = DEFAULT_CONFIG.copy()
    
    if args.config:
        file_config = load_config(args.config)
        config.update(file_config)
    
    # Override with command line arguments
    config["sampling"]["interval_seconds"] = args.interval
    config["logging"]["directory"] = args.log_dir
    if args.verbose:
        config["logging"]["level"] = "DEBUG"
    
    # Create and run application
    app = SmartSniffer(config=config, simulate=args.simulate)
    app.run()


if __name__ == "__main__":
    main()

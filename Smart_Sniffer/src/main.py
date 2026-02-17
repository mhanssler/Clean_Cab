"""
Smart Sniffer - AV Cabin Air Quality Monitor
Main application for BME688-based foul odor detection in autonomous vehicles.

Features:
- 1Hz periodic sampling of cabin air
- Real-time odor classification
- Alert generation for HVAC and fleet management integration
- Data logging for analysis and model training
"""

import sys
import time
import signal
import logging
import argparse
import copy
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
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
        "serial_port": "COM5",
        "baudrate": 115200,
        "timeout_seconds": 2.0,
        "startup_delay_seconds": 2.0
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

# Session modes and labeling for data collection
RUN_MODE_MONITOR = "monitor"
RUN_MODE_BASELINE = "baseline"
RUN_MODE_ODOR_TEST = "odor_test"

RUN_MODE_CHOICES = [
    RUN_MODE_MONITOR,
    RUN_MODE_BASELINE,
    RUN_MODE_ODOR_TEST,
]

TEST_TYPE_CHOICES = [
    "monitor_unlabeled",
    "baseline_clean_air",
    "body_odor",
    "flatulence",
    "bad_breath",
    "food_strong",
    "food_fast",
    "smoke",
    "illness",
    "unknown_foul",
    "mixed",
]

DEFAULT_TEST_TYPE_BY_MODE = {
    RUN_MODE_MONITOR: "monitor_unlabeled",
    RUN_MODE_BASELINE: "baseline_clean_air",
    RUN_MODE_ODOR_TEST: "unknown_foul",
}

EXPECTED_ODOR_CLASS_BY_TEST_TYPE = {
    "monitor_unlabeled": None,
    "baseline_clean_air": OdorClass.CLEAN.name,
    "body_odor": OdorClass.BODY_ODOR.name,
    "flatulence": OdorClass.FLATULENCE.name,
    "bad_breath": OdorClass.BAD_BREATH.name,
    "food_strong": OdorClass.FOOD_STRONG.name,
    "food_fast": OdorClass.FOOD_FAST.name,
    "smoke": OdorClass.SMOKE.name,
    "illness": OdorClass.ILLNESS.name,
    "unknown_foul": OdorClass.UNKNOWN_FOUL.name,
    "mixed": None,
}


def _normalize_test_type(value: str) -> str:
    """Normalize test type token for consistent labeling."""
    return value.strip().lower().replace("-", "_")


def _parse_test_type(value: str) -> str:
    """Argparse type parser for test type labels."""
    normalized = _normalize_test_type(value)
    if normalized not in TEST_TYPE_CHOICES:
        allowed = ", ".join(TEST_TYPE_CHOICES)
        raise argparse.ArgumentTypeError(
            f"Invalid test type '{value}'. Choose one of: {allowed}"
        )
    return normalized


def _resolve_test_type(run_mode: str, requested_test_type: Optional[str]) -> str:
    """Resolve effective test type based on run mode and optional override."""
    if requested_test_type:
        return requested_test_type
    return DEFAULT_TEST_TYPE_BY_MODE[run_mode]


def _build_session_metadata(args: argparse.Namespace) -> Dict[str, Any]:
    """Build session metadata stored on every data record."""
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_type = _resolve_test_type(args.run_mode, args.test_type)
    session_label = args.session_label or f"{args.run_mode}_{test_type}_{session_id}"

    return {
        "session_id": session_id,
        "session_mode": args.run_mode,
        "test_type": test_type,
        "expected_odor_class": EXPECTED_ODOR_CLASS_BY_TEST_TYPE.get(test_type),
        "session_label": session_label,
        "session_notes": args.notes or "",
    }


def _validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Validate CLI argument combinations for intuitive run modes."""
    requested_test_type = args.test_type
    args.test_type = _resolve_test_type(args.run_mode, args.test_type)

    if args.interval <= 0:
        parser.error("--interval must be greater than 0 seconds.")

    if args.duration is not None and args.duration <= 0:
        parser.error("--duration must be greater than 0 seconds.")

    if args.baud is not None and args.baud <= 0:
        parser.error("--baud must be greater than 0.")

    if args.serial_timeout is not None and args.serial_timeout <= 0:
        parser.error("--serial-timeout must be greater than 0 seconds.")

    if (
        args.run_mode == RUN_MODE_BASELINE and
        args.test_type != "baseline_clean_air"
    ):
        parser.error(
            "Baseline mode only supports --test-type baseline_clean_air."
        )

    if args.run_mode == RUN_MODE_ODOR_TEST and requested_test_type is None:
        parser.error(
            "Odor test mode requires --test-type so collected data is labeled."
        )

    if args.run_mode == RUN_MODE_ODOR_TEST and args.test_type in {
        "monitor_unlabeled",
        "baseline_clean_air",
    }:
        parser.error(
            "Odor test mode requires an odor label, "
            "for example --test-type body_odor."
        )


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for Smart Sniffer."""
    parser = argparse.ArgumentParser(
        description="Smart Sniffer - AV Cabin Air Quality Monitor"
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to configuration file (JSON)"
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
    parser.add_argument(
        "--run-mode",
        choices=RUN_MODE_CHOICES,
        default=RUN_MODE_MONITOR,
        help=(
            "Session mode: monitor (normal), baseline (clean-air calibration), "
            "or odor_test (labeled odor capture)"
        )
    )
    parser.add_argument(
        "--test-type",
        type=_parse_test_type,
        help=(
            "Label for this data collection run. "
            "Examples: baseline_clean_air, body_odor, flatulence, smoke."
        )
    )
    parser.add_argument(
        "--session-label",
        help="Human-readable session label stored with each data point"
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional notes stored with the session data"
    )
    parser.add_argument(
        "--duration",
        type=float,
        help="Optional auto-stop duration in seconds"
    )
    parser.add_argument(
        "--port",
        help="Arduino serial port (for example COM5 or /dev/ttyACM0)"
    )
    parser.add_argument(
        "--baud",
        type=int,
        help="Arduino serial baud rate (default: 115200)"
    )
    parser.add_argument(
        "--serial-timeout",
        type=float,
        help="Serial read timeout in seconds"
    )
    return parser


def parse_cli_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse and validate CLI arguments."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    _validate_args(args, parser)
    return args


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dictionaries, preserving nested defaults."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


class SmartSniffer:
    """
    Main application class for AV Cabin Air Quality monitoring.
    """
    
    def __init__(
        self,
        config: Optional[dict] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
        run_duration_seconds: Optional[float] = None
    ):
        """
        Initialize Smart Sniffer.
        
        Args:
            config: Configuration dictionary
            session_metadata: Labels and metadata attached to all logged data
            run_duration_seconds: Optional auto-stop runtime in seconds
        """
        self.config = _deep_merge_dict(DEFAULT_CONFIG, config or {})
        self.session_metadata = dict(session_metadata or {})
        self.run_mode = self.session_metadata.get("session_mode", RUN_MODE_MONITOR)
        self.test_type = self.session_metadata.get(
            "test_type",
            DEFAULT_TEST_TYPE_BY_MODE[RUN_MODE_MONITOR]
        )
        self.session_label = self.session_metadata.get("session_label", "")
        self.run_duration_seconds = run_duration_seconds
        self._alerts_enabled = self.run_mode != RUN_MODE_BASELINE
        
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
            # Initialize sensor from Arduino serial stream
            self.logger.info("Connecting to Arduino BME688 serial stream...")
            self.sensor = BME688(
                serial_port=self.config["sensor"]["serial_port"],
                baudrate=self.config["sensor"]["baudrate"],
                timeout_seconds=self.config["sensor"]["timeout_seconds"],
                startup_delay_seconds=self.config["sensor"]["startup_delay_seconds"]
            )
            self.logger.info(
                "Arduino stream connected on %s @ %s baud",
                self.config["sensor"]["serial_port"],
                self.config["sensor"]["baudrate"]
            )
            
            # Initialize classifier
            self.classifier = OdorClassifier()
            self.logger.info("Odor classifier initialized")
            
            # Initialize alert manager
            self.alert_manager = AlertManager()
            
            # Register alert handlers
            if self._alerts_enabled:
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
            else:
                self.logger.info("Baseline mode enabled: alert dispatch is disabled.")
            
            self.logger.info("Alert manager initialized")
            
            # Initialize data logger
            log_config = LogConfig(
                log_directory=self.config["logging"]["directory"],
                csv_enabled=self.config["logging"]["csv_enabled"],
                json_enabled=self.config["logging"]["json_enabled"],
                session_metadata=self.session_metadata
            )
            self.data_logger = DataLogger(log_config)
            self.data_logger.start()
            self.data_logger.log_custom({"event_name": "session_start"})
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
        """Read from sensor hardware."""
        if self.sensor is None:
            raise RuntimeError("Sensor is not initialized.")
        return self.sensor.read()
    
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
            f"warmup: {warmup}s, run_mode: {self.run_mode}, "
            f"test_type: {self.test_type})"
        )
        
        print("\n" + "="*60)
        print("  SMART SNIFFER - AV Cabin Air Quality Monitor")
        print("="*60)
        print(f"  Sampling Rate: {1/interval:.1f} Hz")
        print(f"  Warmup Period: {warmup} seconds")
        print(
            "  Sensor Mode: Arduino Serial "
            f"({self.config['sensor']['serial_port']} @ {self.config['sensor']['baudrate']})"
        )
        print(f"  Run Mode: {self.run_mode}")
        print(f"  Test Type: {self.test_type}")
        if self.session_label:
            print(f"  Session Label: {self.session_label}")
        if self.run_duration_seconds is not None:
            print(f"  Max Duration: {self.run_duration_seconds:.0f} seconds")
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
                    alerts = []
                    if self._alerts_enabled:
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

                # Optional auto-stop for controlled test runs
                if self.run_duration_seconds is not None:
                    runtime = time.time() - self._start_time
                    if runtime >= self.run_duration_seconds:
                        self.logger.info(
                            "Requested session duration reached "
                            f"({self.run_duration_seconds:.1f}s); stopping."
                        )
                        self._running = False
                    
        finally:
            self.shutdown()
    
    def _display_status(self, reading: SensorReading, event: OdorEvent) -> None:
        """Display current status to console."""
        runtime = time.time() - self._start_time
        
        # Status line
        status_parts = [
            f"T:{reading.temperature:5.1f}C",
            f"H:{reading.humidity:5.1f}%",
            f"P:{reading.pressure:7.1f}hPa",
            f"Gas:{reading.gas_resistance:8.0f} Ohm"
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
            self.data_logger.log_custom(
                {
                    "event_name": "session_end",
                    "summary": dict(self._stats),
                }
            )
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
            print(f"  Baseline Resistance: {stats['baseline_resistance']:.0f} Ohm"
                  if stats['baseline_resistance'] else "  Baseline: Not established")
        
        print("="*60 + "\n")
    
    def get_status(self) -> dict:
        """Get current system status."""
        return {
            "running": self._running,
            "mode": "live",
            "run_mode": self.run_mode,
            "test_type": self.test_type,
            "session_label": self.session_label,
            "sample_count": self._sample_count,
            "runtime": time.time() - self._start_time if self._start_time else 0,
            "stats": self._stats,
            "classifier": self.classifier.get_statistics() if self.classifier else None,
            "alerts": self.alert_manager.get_statistics() if self.alert_manager else None,
            "logging": self.data_logger.get_statistics() if self.data_logger else None,
            "session_metadata": dict(self.session_metadata),
        }


def load_config(config_path: str) -> dict:
    """Load configuration from JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    """Main entry point."""
    args = parse_cli_args()
    session_metadata = _build_session_metadata(args)

    # Build configuration with nested defaults
    config = _deep_merge_dict(DEFAULT_CONFIG, {})
    
    if args.config:
        file_config = load_config(args.config)
        config = _deep_merge_dict(config, file_config)
    
    # Override with command line arguments
    config["sampling"]["interval_seconds"] = args.interval
    config["logging"]["directory"] = args.log_dir
    if args.port:
        config["sensor"]["serial_port"] = args.port
    if args.baud is not None:
        config["sensor"]["baudrate"] = args.baud
    if args.serial_timeout is not None:
        config["sensor"]["timeout_seconds"] = args.serial_timeout
    if args.verbose:
        config["logging"]["level"] = "DEBUG"
    
    # Create and run application
    app = SmartSniffer(
        config=config,
        session_metadata=session_metadata,
        run_duration_seconds=args.duration
    )
    app.run()


if __name__ == "__main__":
    main()


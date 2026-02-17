"""
Data Logger for Smart Sniffer
Logs sensor readings and events for analysis and training data collection.
"""

import os
import json
import csv
import time
import gzip
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import threading
from queue import Queue, Empty

from .bme688_driver import SensorReading
from .odor_classifier import OdorEvent


@dataclass
class LogConfig:
    """Configuration for data logging."""
    log_directory: str = "logs"
    csv_enabled: bool = True
    json_enabled: bool = True
    max_file_size_mb: float = 10.0
    max_files: int = 100
    compress_old_files: bool = True
    flush_interval_seconds: float = 5.0
    buffer_size: int = 100


class DataLogger:
    """
    Asynchronous data logger for sensor readings and events.
    Supports CSV and JSON formats with automatic rotation.
    """
    
    def __init__(self, config: Optional[LogConfig] = None):
        self.config = config or LogConfig()
        
        # Ensure log directory exists
        self._log_dir = Path(self.config.log_directory)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        
        # File handles
        self._csv_file = None
        self._csv_writer = None
        self._json_file = None
        
        # Current log date (for daily rotation)
        self._current_date: Optional[str] = None
        
        # Async logging
        self._queue: Queue = Queue()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._stats = {
            "readings_logged": 0,
            "events_logged": 0,
            "files_rotated": 0,
            "errors": 0
        }
        
        # Buffer for batch writes
        self._buffer: List[dict] = []
        self._last_flush = time.time()
    
    def start(self) -> None:
        """Start the async logging worker."""
        if self._running:
            return
        
        self._running = True
        self._rotate_files_if_needed()
        
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="DataLogger-Worker"
        )
        self._worker_thread.start()
    
    def stop(self) -> None:
        """Stop the logging worker and flush remaining data."""
        self._running = False
        
        if self._worker_thread:
            self._queue.put(None)  # Signal to stop
            self._worker_thread.join(timeout=5.0)
        
        self._flush_buffer()
        self._close_files()
    
    def log_reading(self, reading: SensorReading) -> None:
        """Queue a sensor reading for logging."""
        if self._running:
            self._queue.put(("reading", reading))
    
    def log_event(self, event: OdorEvent) -> None:
        """Queue an odor event for logging."""
        if self._running:
            self._queue.put(("event", event))
    
    def log_custom(self, data: dict) -> None:
        """Queue custom data for logging."""
        if self._running:
            self._queue.put(("custom", data))
    
    def _worker_loop(self) -> None:
        """Background worker for async logging."""
        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
                
                if item is None:
                    break
                
                item_type, data = item
                self._process_item(item_type, data)
                
                # Check if we need to flush
                if (len(self._buffer) >= self.config.buffer_size or
                    time.time() - self._last_flush >= self.config.flush_interval_seconds):
                    self._flush_buffer()
                
            except Empty:
                # Periodic flush even if no new data
                if self._buffer and time.time() - self._last_flush >= self.config.flush_interval_seconds:
                    self._flush_buffer()
                continue
            except Exception as e:
                self._stats["errors"] += 1
        
        # Final flush on exit
        self._flush_buffer()
    
    def _process_item(self, item_type: str, data: Any) -> None:
        """Process a single log item."""
        self._rotate_files_if_needed()
        
        timestamp = time.time()
        dt = datetime.fromtimestamp(timestamp)
        
        if item_type == "reading":
            record = {
                "type": "reading",
                "timestamp": timestamp,
                "datetime": dt.isoformat(),
                "temperature": round(data.temperature, 2),
                "humidity": round(data.humidity, 2),
                "pressure": round(data.pressure, 2),
                "gas_resistance": round(data.gas_resistance, 2)
            }
            self._stats["readings_logged"] += 1
            
        elif item_type == "event":
            record = {
                "type": "event",
                "timestamp": timestamp,
                "datetime": dt.isoformat(),
                "odor_class": data.odor_class.name,
                "severity": data.severity.name,
                "confidence": round(data.confidence, 3),
                "gas_resistance": round(data.gas_resistance, 2),
                "temperature": round(data.temperature, 2),
                "humidity": round(data.humidity, 2)
            }
            self._stats["events_logged"] += 1
            
        elif item_type == "custom":
            record = {
                "type": "custom",
                "timestamp": timestamp,
                "datetime": dt.isoformat(),
                **data
            }
        else:
            return
        
        self._buffer.append(record)
    
    def _flush_buffer(self) -> None:
        """Write buffered data to files."""
        if not self._buffer:
            return
        
        try:
            # Write to CSV
            if self.config.csv_enabled and self._csv_writer:
                for record in self._buffer:
                    flat_record = self._flatten_record(record)
                    self._csv_writer.writerow(flat_record)
                self._csv_file.flush()
            
            # Write to JSON (one object per line - JSON Lines format)
            if self.config.json_enabled and self._json_file:
                for record in self._buffer:
                    self._json_file.write(json.dumps(record) + "\n")
                self._json_file.flush()
            
            self._buffer.clear()
            self._last_flush = time.time()
            
        except Exception as e:
            self._stats["errors"] += 1
    
    def _flatten_record(self, record: dict) -> dict:
        """Flatten nested dict for CSV writing."""
        flat = {}
        for key, value in record.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    flat[f"{key}_{sub_key}"] = sub_value
            else:
                flat[key] = value
        return flat
    
    def _rotate_files_if_needed(self) -> None:
        """Check if files need rotation (daily or size-based)."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Daily rotation
        if self._current_date != current_date:
            self._close_files()
            self._current_date = current_date
            self._open_files()
            return
        
        # Size-based rotation
        if self._csv_file:
            try:
                size_mb = os.path.getsize(self._csv_file.name) / (1024 * 1024)
                if size_mb >= self.config.max_file_size_mb:
                    self._rotate_current_files()
            except:
                pass
    
    def _open_files(self) -> None:
        """Open new log files for the current date."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if self.config.csv_enabled:
            csv_path = self._log_dir / f"readings_{timestamp}.csv"
            self._csv_file = open(csv_path, 'w', newline='')
            self._csv_writer = csv.DictWriter(
                self._csv_file,
                fieldnames=[
                    "type", "timestamp", "datetime",
                    "temperature", "humidity", "pressure", "gas_resistance",
                    "odor_class", "severity", "confidence"
                ],
                extrasaction='ignore'
            )
            self._csv_writer.writeheader()
        
        if self.config.json_enabled:
            json_path = self._log_dir / f"readings_{timestamp}.jsonl"
            self._json_file = open(json_path, 'w')
    
    def _close_files(self) -> None:
        """Close current log files."""
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
        
        if self._json_file:
            self._json_file.close()
            self._json_file = None
    
    def _rotate_current_files(self) -> None:
        """Rotate current files due to size limit."""
        csv_path = self._csv_file.name if self._csv_file else None
        json_path = self._json_file.name if self._json_file else None
        
        self._close_files()
        
        # Compress old files if enabled
        if self.config.compress_old_files:
            if csv_path and os.path.exists(csv_path):
                self._compress_file(csv_path)
            if json_path and os.path.exists(json_path):
                self._compress_file(json_path)
        
        self._open_files()
        self._stats["files_rotated"] += 1
        
        # Clean up old files
        self._cleanup_old_files()
    
    def _compress_file(self, filepath: str) -> None:
        """Compress a file using gzip."""
        try:
            with open(filepath, 'rb') as f_in:
                with gzip.open(f"{filepath}.gz", 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.remove(filepath)
        except Exception:
            pass
    
    def _cleanup_old_files(self) -> None:
        """Remove oldest files if max_files exceeded."""
        try:
            files = sorted(
                self._log_dir.glob("readings_*"),
                key=lambda f: f.stat().st_mtime
            )
            
            while len(files) > self.config.max_files:
                oldest = files.pop(0)
                oldest.unlink()
                
        except Exception:
            pass
    
    def get_statistics(self) -> dict:
        """Get logging statistics."""
        return {
            **self._stats,
            "buffer_size": len(self._buffer),
            "queue_size": self._queue.qsize()
        }
    
    def export_session(
        self, 
        output_path: str,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> str:
        """
        Export logged data for a time range to a single file.
        Useful for training data collection.
        """
        self._flush_buffer()
        
        records = []
        
        # Read from all JSONL files
        for json_file in sorted(self._log_dir.glob("readings_*.jsonl")):
            try:
                with open(json_file, 'r') as f:
                    for line in f:
                        record = json.loads(line)
                        ts = record.get("timestamp", 0)
                        
                        if start_time and ts < start_time:
                            continue
                        if end_time and ts > end_time:
                            continue
                        
                        records.append(record)
            except:
                continue
        
        # Write to output file
        with open(output_path, 'w') as f:
            json.dump({
                "export_time": datetime.now().isoformat(),
                "record_count": len(records),
                "data": records
            }, f, indent=2)
        
        return output_path
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False

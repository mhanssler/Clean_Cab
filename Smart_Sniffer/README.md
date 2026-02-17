# Smart Sniffer 🐽

**AV Cabin Air Quality Monitor** - BME688-based foul odor detection for autonomous vehicles.

Detects and classifies human-generated odors in autonomous vehicle cabins, enabling automatic HVAC response and fleet management notifications.

## Target Odors

| Odor Class | Description | Typical Response |
|------------|-------------|------------------|
| Body Odor | Perspiration, sweat | Increase ventilation |
| Flatulence | Intestinal gas | Maximum ventilation |
| Bad Breath | Halitosis | Moderate ventilation |
| Food (Strong) | Garlic, onion, fish, curry | Extended ventilation |
| Food (Fast) | Fried foods, fast food | Increase ventilation |
| Smoke | Cigarette/vape residue | Alert + ventilation |
| Illness | Vomit indicators | Emergency protocol |

## Hardware Requirements

### Minimum (Raspberry Pi B+)
- Raspberry Pi 1 Model B+ (512MB RAM, ARM11)
- BME688 Breakout Board (Adafruit, Pimoroni, or similar)
- MicroSD Card (8GB+)
- 5V 2A Power Supply

### Recommended Upgrade
- Raspberry Pi Zero 2 W (~$15) - Better performance for AI features
- Raspberry Pi 4 - Best performance and expandability

### Wiring (I2C)

| BME688 Pin | Raspberry Pi Pin |
|------------|------------------|
| VIN | 3.3V (Pin 1) |
| GND | Ground (Pin 6) |
| SDA | GPIO 2 (Pin 3) |
| SCL | GPIO 3 (Pin 5) |

## Installation

### 1. Raspberry Pi Setup

```bash
# Enable I2C
sudo raspi-config
# Interface Options → I2C → Enable

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python dependencies
sudo apt install -y python3-pip python3-smbus i2c-tools

# Verify sensor connection
i2cdetect -y 1
# Should show 0x76 or 0x77
```

### 2. Install Smart Sniffer

```bash
# Clone or copy project
cd /home/pi
git clone <repository> Smart_Sniffer
cd Smart_Sniffer

# Install Python requirements
pip3 install -r requirements.txt
```

### 3. Run

```bash
# Live sensor mode
python3 -m src.main

# Simulation mode (no sensor required)
python3 -m src.main --simulate

# Custom configuration
python3 -m src.main --config config/default_config.json

# Baseline data collection (clean air, 5 minutes)
python3 -m src.main --run-mode baseline --duration 300 --test-type baseline_clean_air

# Labeled odor test data collection (smoke example)
python3 -m src.main --run-mode odor_test --test-type smoke --duration 180 --notes "rear seat sample"
```

## Usage

### Command Line Options

```
usage: main.py [-h] [-c CONFIG] [-s] [-i INTERVAL] [-l LOG_DIR] [-v]
               [--run-mode {monitor,baseline,odor_test}] [--test-type TEST_TYPE]
               [--session-label SESSION_LABEL] [--notes NOTES] [--duration DURATION]

Smart Sniffer - AV Cabin Air Quality Monitor

optional arguments:
  -h, --help            show this help message and exit
  -c, --config CONFIG   Path to configuration file (JSON)
  -s, --simulate        Run in simulation mode (no sensor required)
  -i, --interval FLOAT  Sampling interval in seconds (default: 1.0)
  -l, --log-dir DIR     Log directory (default: logs)
  -v, --verbose         Enable verbose logging
  --run-mode MODE       monitor, baseline, or odor_test
  --test-type LABEL     Data label for the run (required for odor_test)
  --session-label TEXT  Human-readable session name stored in records
  --notes TEXT          Session notes stored in records
  --duration SECONDS    Auto-stop after a fixed runtime
```

### Recommended Data Collection Flow

1. Run baseline calibration collection:
   ```bash
   python3 -m src.main --run-mode baseline --test-type baseline_clean_air --duration 300
   ```
2. Run one odor test session per target class:
   ```bash
   python3 -m src.main --run-mode odor_test --test-type body_odor --duration 180
   python3 -m src.main --run-mode odor_test --test-type flatulence --duration 180
   python3 -m src.main --run-mode odor_test --test-type smoke --duration 180
   ```
3. Every record is automatically labeled with:
   - `session_mode`
   - `test_type`
   - `expected_odor_class`
   - `session_label`
   - `session_notes`

### Example Output

```
============================================================
  SMART SNIFFER - AV Cabin Air Quality Monitor
============================================================
  Sampling Rate: 1.0 Hz
  Warmup Period: 60 seconds
  Mode: Live Sensor
============================================================

[   45s] T: 23.5°C | H: 42.3% | P: 1013.2hPa | Gas:  52340Ω | [Calibrating 75%]
[   60s] T: 23.4°C | H: 42.1% | P: 1013.1hPa | Gas:  51890Ω | [Air: OK]
[   85s] T: 23.6°C | H: 43.2% | P: 1013.0hPa | Gas:  31250Ω | [FLATULENCE: MODERATE]
⚠️ Air quality notice: Flatulence detected. Fresh air circulation activated.
```

## Project Structure

```
Smart_Sniffer/
├── src/
│   ├── __init__.py
│   ├── main.py              # Main application entry point
│   ├── bme688_driver.py     # BME688 I2C driver
│   ├── odor_classifier.py   # Odor classification logic
│   ├── alerts.py            # Alert management system
│   └── data_logger.py       # Data logging for training
├── config/
│   ├── default_config.json  # System configuration
│   └── odor_profiles.json   # Odor classification profiles
├── logs/                    # Runtime logs and data
├── requirements.txt
└── README.md
```

## Configuration

### Sensor Settings (`config/default_config.json`)

```json
{
  "sensor": {
    "i2c_bus": 1,
    "i2c_address": "0x76",
    "heater_temp": 320,
    "heater_duration_ms": 150
  },
  "sampling": {
    "interval_seconds": 1.0,
    "warmup_seconds": 60
  }
}
```

### Classification Thresholds

| Threshold | Resistance Ratio | Severity |
|-----------|-----------------|----------|
| Low | < 0.70 | Minor odor detected |
| Moderate | < 0.50 | Noticeable odor |
| High | < 0.30 | Strong odor |
| Severe | < 0.15 | Very strong / health concern |

## AV Integration

### HVAC Control

The alert system provides ventilation level recommendations (0-100%) based on odor severity. Integrate with your AV's HVAC system:

```python
from src.alerts import AlertManager, AlertAction, create_hvac_handler

def my_hvac_control(level: int):
    # Send command to AV HVAC system
    # level: 0-100 (percentage)
    pass

alert_manager = AlertManager()
alert_manager.register_handler(
    AlertAction.ACTIVATE_HVAC,
    create_hvac_handler(my_hvac_control)
)
```

### Fleet Management

Configure fleet notification endpoint in `config/default_config.json`:

```json
{
  "alerts": {
    "fleet_notify_enabled": true,
    "fleet_api_url": "https://fleet.example.com/api/events",
    "fleet_api_key": "your-api-key"
  }
}
```

## Training Custom Models

For improved classification accuracy, use Bosch BME AI-Studio:

1. **Collect Training Data**
   ```bash
   # Baseline first
   python3 -m src.main --log-dir training_data --run-mode baseline --test-type baseline_clean_air --duration 300

   # Then labeled odor sessions
   python3 -m src.main --log-dir training_data --run-mode odor_test --test-type smoke --duration 180
   python3 -m src.main --log-dir training_data --run-mode odor_test --test-type food_strong --duration 180
   ```

2. **Export Session Data**
   ```python
   from src.data_logger import DataLogger
   logger = DataLogger()
   logger.export_session("training_export.json")
   ```

3. **Train in BME AI-Studio** (Windows)
   - Import collected data
   - Define odor classes
   - Train classifier
   - Export configuration

4. **Deploy Trained Model**
   - Copy exported config to `config/trained_model.json`
   - Update `odor_profiles.json` with trained parameters

## Limitations

### Raspberry Pi B+ Constraints
- Single-core 700MHz ARM11 limits processing
- 512MB RAM restricts advanced AI models
- Consider upgrading to Pi Zero 2 W or Pi 4 for production

### BME688 Sensor Characteristics
- 48-hour burn-in recommended for new sensors
- 30-minute warmup on each power-on
- Cannot differentiate individual gas compounds without training
- Environmental compensation needed for accuracy

## License

MIT License - See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Support

For issues and feature requests, please open a GitHub issue.

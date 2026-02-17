# Smart Sniffer

Arduino-first BME688 VOC monitoring and data collection for human-odor classification.

## What This Version Targets

- Sensor board: `BME688`
- Controller: `Arduino Mega 2560` (or compatible Arduino)
- Host app: Python on your PC, reading Arduino serial output

This project no longer assumes Raspberry Pi I2C as the primary runtime path.

## Hardware Wiring (Arduino Mega)

- `SDA -> pin 20`
- `SCL -> pin 21`
- `VCC -> module spec` (3.3V or 5V per breakout)
- `GND -> GND`

BME688 I2C address is usually `0x77` (sometimes `0x76` based on SDO wiring).

## Arduino Sketches

- I2C probe / chip-ID check:
  - `arduino/bme688_i2c_test_megacom5/bme688_i2c_test_megacom5.ino`
- Baseline + CSV stream (for host ingestion):
  - `arduino/bme688_baseline_csv_megacom5/bme688_baseline_csv_megacom5.ino`

### Upload Steps

1. Install Arduino library: `Bosch BME68x Library`
2. Open the baseline sketch:
   - `arduino/bme688_baseline_csv_megacom5/bme688_baseline_csv_megacom5.ino`
3. Select board: `Arduino Mega or Mega 2560`
4. Select port: `COM5` (or your board port)
5. Upload

The sketch emits CSV like:

```text
host_ms,sample,temp_c,pressure_pa,humidity_pct,gas_ohm,baseline_ohm,gas_ratio,gas_delta_pct,phase,status_hex
```

## Python Setup

```bash
pip install -r requirements.txt
```

## Run the Host App (Live Classification + Logging)

```bash
python -m src.main --port COM5 --baud 115200
```

Useful options:

```text
--port COM5               Arduino serial port
--baud 115200             Serial baud rate
--serial-timeout 2.0      Read timeout in seconds
--run-mode monitor        monitor | baseline | odor_test
--test-type body_odor     Label for odor_test runs
--duration 180            Auto-stop run length (seconds)
--log-dir logs            Output directory
```

### Example Sessions

Baseline capture:

```bash
python -m src.main --port COM5 --run-mode baseline --test-type baseline_clean_air --duration 300
```

Labeled odor capture:

```bash
python -m src.main --port COM5 --run-mode odor_test --test-type body_odor --duration 180
python -m src.main --port COM5 --run-mode odor_test --test-type smoke --duration 180
```

## Standalone Serial-to-CSV Capture Tool

If you only want raw Arduino stream capture:

```bash
python tools/capture_bme688_serial_to_csv.py --port COM5 --baud 115200 --duration 300 --label clean
```


## Baseline vs Class Analysis Tool

Generate a baseline-comparison report across all class folders in `logs/`:

```bash
python tools/analyze_baseline_vs_classes.py --logs-root logs --baseline-folder Baseline
```

Optional output directory:

```bash
python tools/analyze_baseline_vs_classes.py --logs-root logs --baseline-folder Baseline --out-dir logs/analysis
```

The tool writes:
- `logs/analysis/baseline_vs_classes_YYYYMMDD_HHMMSS.md`
- `logs/analysis/baseline_vs_classes_YYYYMMDD_HHMMSS.json`

## Data Outputs

- Main app:
  - `logs/readings_*.csv`
  - `logs/readings_*.jsonl`
  - `logs/smart_sniffer_YYYYMMDD.log`
- Capture tool:
  - `logs/bme688_capture_YYYYMMDD_HHMMSS.csv`
- Analysis tool:
  - `logs/analysis/baseline_vs_classes_YYYYMMDD_HHMMSS.md`
  - `logs/analysis/baseline_vs_classes_YYYYMMDD_HHMMSS.json`

## Project Structure

```text
Smart_Sniffer/
|-- arduino/
|   |-- bme688_i2c_test_megacom5/
|   |-- bme688_baseline_csv_megacom5/
|-- tools/
|   |-- capture_bme688_serial_to_csv.py
|   |-- analyze_baseline_vs_classes.py
|-- src/
|   |-- main.py
|   |-- bme688_driver.py
|   |-- odor_classifier.py
|   |-- alerts.py
|   |-- data_logger.py
|-- config/
|   |-- default_config.json
|   |-- odor_profiles.json
|-- tests/
|-- requirements.txt
```

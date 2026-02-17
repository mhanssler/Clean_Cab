"""
Capture CSV lines from an Arduino BME688 serial stream and store to a CSV file.

Default settings target:
- Port: COM5
- Baud: 115200
- Input sketch: arduino/bme688_baseline_csv_megacom5
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import serial


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture BME688 CSV stream from Arduino serial to logs/*.csv"
    )
    parser.add_argument("--port", default="COM5", help="Serial port (default: COM5)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Capture duration in seconds (0 = run until Ctrl+C)",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output CSV file path (default: logs/bme688_capture_<timestamp>.csv)",
    )
    parser.add_argument(
        "--label",
        default="unknown",
        choices=["clean", "body_odor", "vomit", "feces", "urine", "unknown"],
        help="Session label added to each row for training",
    )
    return parser.parse_args()


def build_output_path(out_arg: str) -> Path:
    if out_arg:
        out_path = Path(out_arg)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path("logs") / f"bme688_capture_{ts}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


def is_data_row(parts: list[str]) -> bool:
    if len(parts) != 11:
        return False
    try:
        int(parts[0])  # host_ms
        int(parts[1])  # sample
        float(parts[2])  # temp
        float(parts[3])  # pressure
        float(parts[4])  # humidity
        float(parts[5])  # gas
        float(parts[6])  # baseline
        float(parts[7])  # ratio
        float(parts[8])  # delta %
    except ValueError:
        return False
    return True


def main() -> int:
    args = parse_args()
    out_path = build_output_path(args.out)

    print(f"Opening {args.port} @ {args.baud}...")
    ser = serial.Serial(args.port, args.baud, timeout=1)
    time.sleep(2.0)  # give board time to reset and print header

    start = time.time()
    rows = 0
    header_written = False
    expected_header = [
        "host_ms",
        "sample",
        "temp_c",
        "pressure_pa",
        "humidity_pct",
        "gas_ohm",
        "baseline_ohm",
        "gas_ratio",
        "gas_delta_pct",
        "phase",
        "status_hex",
        "label",
    ]

    try:
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            while True:
                if args.duration > 0 and (time.time() - start) >= args.duration:
                    break

                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                if line.startswith("#"):
                    print(line)
                    continue

                if line.startswith("host_ms,"):
                    if not header_written:
                        writer.writerow(expected_header)
                        header_written = True
                        print(f"Header detected. Writing to {out_path}")
                    continue

                parts = [p.strip() for p in line.split(",")]
                if not is_data_row(parts):
                    print(f"Skipping non-data line: {line}")
                    continue

                if not header_written:
                    writer.writerow(expected_header)
                    header_written = True

                writer.writerow(parts + [args.label])
                rows += 1

                if rows % 10 == 0:
                    f.flush()
                    print(f"Captured rows: {rows}", end="\r", flush=True)

    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

    print(f"\nDone. Wrote {rows} data rows to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
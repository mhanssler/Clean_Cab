#!/bin/bash
# Smart Sniffer setup script (Arduino serial workflow)
# Run with: bash install.sh

set -e

echo "========================================"
echo "  Smart Sniffer Setup"
echo "========================================"

echo "[1/2] Installing Python dependencies..."
python3 -m pip install --user -r requirements.txt

echo "[2/2] Creating runtime directories..."
mkdir -p logs
mkdir -p arduino
mkdir -p tools

echo ""
echo "========================================"
echo "  Setup Complete"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Upload: arduino/bme688_baseline_csv_megacom5/bme688_baseline_csv_megacom5.ino"
echo "2. Connect board over USB (example COM5 on Windows)"
echo "3. Run host app: python3 -m src.main --port COM5 --baud 115200"
echo "4. Or capture raw CSV: python3 tools/capture_bme688_serial_to_csv.py --port COM5"
echo ""

#!/bin/bash
# Smart Sniffer Installation Script for Raspberry Pi
# Run with: bash install.sh

set -e

echo "========================================"
echo "  Smart Sniffer Installation"
echo "========================================"

# Check if running on Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "[1/5] Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install system dependencies
echo "[2/5] Installing system dependencies..."
sudo apt install -y \
    python3-pip \
    python3-smbus \
    python3-dev \
    i2c-tools \
    git

# Enable I2C if not already enabled
echo "[3/5] Configuring I2C..."
if ! grep -q "^dtparam=i2c_arm=on" /boot/config.txt; then
    echo "dtparam=i2c_arm=on" | sudo tee -a /boot/config.txt
    echo "I2C enabled in config.txt (reboot required)"
fi

if ! lsmod | grep -q i2c_bcm2835; then
    sudo modprobe i2c-bcm2835
fi

# Install Python dependencies
echo "[4/5] Installing Python dependencies..."
pip3 install --user -r requirements.txt

# Create logs directory
echo "[5/5] Setting up directories..."
mkdir -p logs

# Verify I2C connection
echo ""
echo "========================================"
echo "  Checking I2C Connection"
echo "========================================"
echo "Running i2cdetect -y 1..."
i2cdetect -y 1 || echo "I2C detection failed - sensor may not be connected"

echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Connect BME688 sensor to I2C pins"
echo "2. Reboot if I2C was just enabled: sudo reboot"
echo "3. Run: python3 -m src.main"
echo "4. Or test with: python3 -m src.main --simulate"
echo ""

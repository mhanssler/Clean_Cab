# Rigol Multi-Instrument Control System

## Overview
Professional GUI application for controlling Rigol laboratory equipment via SSH connection to Raspberry Pi.

## Supported Instruments
- **DP832**: 3-Channel Power Supply
- **DL3000**: Electronic Load  
- **DS1102E**: Digital Storage Oscilloscope

## Features
- Real-time measurement displays with auto-refresh
- Interactive instrument controls
- Live data plotting and visualization
- Professional tabbed interface
- Emergency shutdown controls
- Dynamic text scaling for different screen sizes
- Command verification with retry logic
- Consistent widget sizing and styling across all tabs
- Dark theme with responsive typography

## Quick Start
1. Install dependencies: `pip install -r requirements_gui.txt`
2. Run the GUI: `launch_gui.bat` or `python Rigol_Multi_Instrument_GUI.py`
3. Connect to instruments via the connection interface

## UI Enhancements (October 2025)
- Unified section and subsection cards across Overview, Power Supply, Load, Oscilloscope, Log, and Diagnostics tabs for a consistent look.
- Font, scale, combo-box, and tree-view dimensions now auto-scale with window resizing for improved readability on high-DPI displays.
- Control rows in the Power Supply and Electronic Load tabs now align via grid layouts, keeping sliders, entries, and action buttons in fixed columns.
- Oscilloscope controls reorganized into balanced groups with clearly labeled capture actions and channel settings.
- Diagnostics tab refreshed with responsive tables, streamlined padding, and quick action buttons for exporting or clearing command history.
- Status bar spacing tuned to match the rest of the interface while maintaining at-a-glance indicators.

## Files
- `Rigol_Multi_Instrument_GUI.py` - Main GUI application
- `Connect_to_Rigol_Instruments.py` - Backend SSH connection utilities
- `launch_gui.bat` - Windows launcher script
- `requirements_gui.txt` - Python dependencies
- `archive_old_files/` - Backup versions and deprecated code

## Connection
Connects to Raspberry Pi via SSH to communicate with USB-connected Rigol instruments.

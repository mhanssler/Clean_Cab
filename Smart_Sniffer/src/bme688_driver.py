"""
BME688 Sensor Driver for Raspberry Pi
I2C interface for temperature, humidity, pressure, and gas resistance readings.
Optimized for Raspberry Pi B+ with periodic 1Hz sampling.
"""

import time
import struct
from typing import Optional, Tuple, NamedTuple
from dataclasses import dataclass

# I2C library - only required for actual hardware
# Simulation mode works without it
_SMBUS_AVAILABLE = False
try:
    import smbus2 as smbus
    _SMBUS_AVAILABLE = True
except ImportError:
    try:
        import smbus
        _SMBUS_AVAILABLE = True
    except ImportError:
        smbus = None  # Will use simulation mode


class SensorReading(NamedTuple):
    """Container for BME688 sensor readings."""
    temperature: float      # Celsius
    humidity: float         # %RH
    pressure: float         # hPa
    gas_resistance: float   # Ohms
    timestamp: float        # Unix timestamp


@dataclass
class HeaterProfile:
    """Heater configuration for gas sensing."""
    temperature: int = 320      # Heater temperature in Celsius (200-400)
    duration_ms: int = 150      # Heating duration in milliseconds
    

class BME688:
    """
    BME688 Environmental Sensor Driver
    
    Supports I2C communication for reading:
    - Temperature (-40 to 85°C)
    - Humidity (0-100% RH)
    - Pressure (300-1100 hPa)
    - Gas Resistance (VOC detection)
    """
    
    # I2C Address (0x76 or 0x77 depending on SDO pin)
    DEFAULT_I2C_ADDRESS = 0x76
    ALT_I2C_ADDRESS = 0x77
    
    # Register addresses
    REG_CHIP_ID = 0xD0
    REG_RESET = 0xE0
    REG_CTRL_HUM = 0x72
    REG_CTRL_MEAS = 0x74
    REG_CTRL_GAS_0 = 0x70
    REG_CTRL_GAS_1 = 0x71
    REG_GAS_WAIT_0 = 0x64
    REG_RES_HEAT_0 = 0x5A
    REG_STATUS = 0x1D
    REG_DATA_START = 0x1D
    
    # Chip ID for BME688
    CHIP_ID_BME688 = 0x61
    
    # Oversampling settings
    OS_NONE = 0
    OS_1X = 1
    OS_2X = 2
    OS_4X = 3
    OS_8X = 4
    OS_16X = 5
    
    # Operating modes
    MODE_SLEEP = 0
    MODE_FORCED = 1
    
    def __init__(
        self, 
        i2c_bus: int = 1, 
        address: int = DEFAULT_I2C_ADDRESS,
        temp_os: int = OS_2X,
        hum_os: int = OS_2X,
        pres_os: int = OS_2X
    ):
        """
        Initialize BME688 sensor.
        
        Args:
            i2c_bus: I2C bus number (1 for Pi B+)
            address: I2C address (0x76 or 0x77)
            temp_os: Temperature oversampling
            hum_os: Humidity oversampling
            pres_os: Pressure oversampling
        """
        self.address = address
        self.bus = smbus.SMBus(i2c_bus)
        
        self.temp_os = temp_os
        self.hum_os = hum_os
        self.pres_os = pres_os
        
        # Calibration data (loaded on init)
        self._cal_data = {}
        
        # Heater profile for gas sensing
        self.heater_profile = HeaterProfile()
        
        # Initialize sensor
        self._init_sensor()
    
    def _init_sensor(self) -> None:
        """Initialize and configure the sensor."""
        # Verify chip ID
        chip_id = self._read_byte(self.REG_CHIP_ID)
        if chip_id != self.CHIP_ID_BME688:
            raise RuntimeError(
                f"BME688 not found. Expected chip ID 0x{self.CHIP_ID_BME688:02X}, "
                f"got 0x{chip_id:02X}"
            )
        
        # Soft reset
        self._soft_reset()
        time.sleep(0.01)
        
        # Load calibration data
        self._load_calibration_data()
        
        # Configure humidity oversampling
        self._write_byte(self.REG_CTRL_HUM, self.hum_os)
        
        # Configure heater for gas measurement
        self._configure_heater()
    
    def _soft_reset(self) -> None:
        """Perform soft reset."""
        self._write_byte(self.REG_RESET, 0xB6)
        time.sleep(0.005)
    
    def _read_byte(self, register: int) -> int:
        """Read single byte from register."""
        return self.bus.read_byte_data(self.address, register)
    
    def _read_bytes(self, register: int, length: int) -> bytes:
        """Read multiple bytes from register."""
        return bytes(self.bus.read_i2c_block_data(self.address, register, length))
    
    def _write_byte(self, register: int, value: int) -> None:
        """Write single byte to register."""
        self.bus.write_byte_data(self.address, register, value)
    
    def _load_calibration_data(self) -> None:
        """Load factory calibration data from sensor."""
        # Temperature calibration (par_t1, par_t2, par_t3)
        coeff1 = self._read_bytes(0x8A, 23)
        coeff2 = self._read_bytes(0xE1, 14)
        
        # Parse temperature coefficients
        self._cal_data['par_t1'] = struct.unpack('<H', coeff2[9:11])[0]
        self._cal_data['par_t2'] = struct.unpack('<h', coeff1[0:2])[0]
        self._cal_data['par_t3'] = coeff1[2]
        
        # Pressure coefficients
        self._cal_data['par_p1'] = struct.unpack('<H', coeff1[4:6])[0]
        self._cal_data['par_p2'] = struct.unpack('<h', coeff1[6:8])[0]
        self._cal_data['par_p3'] = coeff1[8]
        self._cal_data['par_p4'] = struct.unpack('<h', coeff1[10:12])[0]
        self._cal_data['par_p5'] = struct.unpack('<h', coeff1[12:14])[0]
        self._cal_data['par_p6'] = coeff1[15]
        self._cal_data['par_p7'] = coeff1[14]
        self._cal_data['par_p8'] = struct.unpack('<h', coeff1[18:20])[0]
        self._cal_data['par_p9'] = struct.unpack('<h', coeff1[20:22])[0]
        self._cal_data['par_p10'] = coeff1[22]
        
        # Humidity coefficients
        self._cal_data['par_h1'] = (coeff2[2] << 4) | (coeff2[1] & 0x0F)
        self._cal_data['par_h2'] = (coeff2[0] << 4) | (coeff2[1] >> 4)
        self._cal_data['par_h3'] = coeff2[3]
        self._cal_data['par_h4'] = coeff2[4]
        self._cal_data['par_h5'] = coeff2[5]
        self._cal_data['par_h6'] = coeff2[6]
        self._cal_data['par_h7'] = coeff2[7]
        
        # Gas calibration coefficients
        self._cal_data['par_g1'] = coeff2[12]
        self._cal_data['par_g2'] = struct.unpack('<h', coeff2[10:12])[0]
        self._cal_data['par_g3'] = coeff2[13]
        
        # Heater range and resistance
        self._cal_data['res_heat_range'] = (self._read_byte(0x02) & 0x30) >> 4
        self._cal_data['res_heat_val'] = self._read_byte(0x00)
        self._cal_data['range_sw_err'] = (self._read_byte(0x04) & 0xF0) >> 4
    
    def _configure_heater(self) -> None:
        """Configure gas heater for VOC measurement."""
        # Calculate heater resistance value
        res_heat = self._calc_heater_resistance(self.heater_profile.temperature)
        self._write_byte(self.REG_RES_HEAT_0, res_heat)
        
        # Set gas wait time (heating duration)
        gas_wait = self._calc_gas_wait(self.heater_profile.duration_ms)
        self._write_byte(self.REG_GAS_WAIT_0, gas_wait)
        
        # Enable gas measurement, select heater profile 0
        self._write_byte(self.REG_CTRL_GAS_1, 0x10)
    
    def _calc_heater_resistance(self, target_temp: int) -> int:
        """Calculate heater resistance register value."""
        par_g1 = self._cal_data['par_g1']
        par_g2 = self._cal_data['par_g2']
        par_g3 = self._cal_data['par_g3']
        res_heat_range = self._cal_data['res_heat_range']
        res_heat_val = self._cal_data['res_heat_val']
        
        # Ambient temperature (approximate)
        amb_temp = 25
        
        var1 = (par_g1 / 16.0) + 49.0
        var2 = ((par_g2 / 32768.0) * 0.0005) + 0.00235
        var3 = par_g3 / 1024.0
        var4 = var1 * (1.0 + (var2 * target_temp))
        var5 = var4 + (var3 * amb_temp)
        res_heat = int(3.4 * ((var5 * (4.0 / (4.0 + res_heat_range)) * 
                              (1.0 / (1.0 + (res_heat_val * 0.002)))) - 25))
        
        return max(0, min(255, res_heat))
    
    def _calc_gas_wait(self, duration_ms: int) -> int:
        """Calculate gas wait register value from duration in ms."""
        if duration_ms < 64:
            return duration_ms
        
        factor = 0
        while duration_ms > 63:
            duration_ms //= 4
            factor += 1
            if factor > 3:
                return 0xFF  # Max duration
        
        return duration_ms + (factor * 64)
    
    def set_heater_profile(self, temperature: int, duration_ms: int) -> None:
        """
        Set heater profile for gas sensing.
        
        Args:
            temperature: Target heater temperature (200-400°C)
            duration_ms: Heating duration in milliseconds
        """
        self.heater_profile.temperature = max(200, min(400, temperature))
        self.heater_profile.duration_ms = max(1, min(4032, duration_ms))
        self._configure_heater()
    
    def read(self) -> SensorReading:
        """
        Perform a single measurement and return all sensor readings.
        
        Returns:
            SensorReading with temperature, humidity, pressure, and gas resistance
        """
        # Set forced mode to trigger measurement
        ctrl_meas = (self.temp_os << 5) | (self.pres_os << 2) | self.MODE_FORCED
        self._write_byte(self.REG_CTRL_MEAS, ctrl_meas)
        
        # Wait for measurement to complete
        # Measurement time depends on oversampling settings
        meas_time = self._calc_measurement_time()
        time.sleep(meas_time)
        
        # Wait for data ready
        for _ in range(10):
            status = self._read_byte(self.REG_STATUS)
            if status & 0x80:  # New data available
                break
            time.sleep(0.01)
        
        # Read raw data
        data = self._read_bytes(self.REG_DATA_START, 17)
        
        # Parse and compensate readings
        timestamp = time.time()
        
        # ADC values
        pres_adc = (data[2] << 12) | (data[3] << 4) | (data[4] >> 4)
        temp_adc = (data[5] << 12) | (data[6] << 4) | (data[7] >> 4)
        hum_adc = (data[8] << 8) | data[9]
        gas_adc = (data[13] << 2) | (data[14] >> 6)
        gas_range = data[14] & 0x0F
        
        # Compensate readings
        temperature, t_fine = self._compensate_temperature(temp_adc)
        pressure = self._compensate_pressure(pres_adc, t_fine)
        humidity = self._compensate_humidity(hum_adc, t_fine)
        gas_resistance = self._compensate_gas(gas_adc, gas_range)
        
        return SensorReading(
            temperature=temperature,
            humidity=humidity,
            pressure=pressure,
            gas_resistance=gas_resistance,
            timestamp=timestamp
        )
    
    def _calc_measurement_time(self) -> float:
        """Calculate approximate measurement time in seconds."""
        # Base times in microseconds
        os_to_time = {0: 0, 1: 1000, 2: 2000, 3: 4000, 4: 8000, 5: 16000}
        
        temp_time = os_to_time.get(self.temp_os, 0)
        pres_time = os_to_time.get(self.pres_os, 0)
        hum_time = os_to_time.get(self.hum_os, 0)
        gas_time = self.heater_profile.duration_ms * 1000
        
        total_us = temp_time + pres_time + hum_time + gas_time + 1000
        return total_us / 1_000_000
    
    def _compensate_temperature(self, adc: int) -> Tuple[float, float]:
        """Compensate raw temperature ADC value."""
        par_t1 = self._cal_data['par_t1']
        par_t2 = self._cal_data['par_t2']
        par_t3 = self._cal_data['par_t3']
        
        var1 = ((adc / 16384.0) - (par_t1 / 1024.0)) * par_t2
        var2 = (((adc / 131072.0) - (par_t1 / 8192.0)) * 
                ((adc / 131072.0) - (par_t1 / 8192.0))) * (par_t3 * 16.0)
        t_fine = var1 + var2
        temperature = t_fine / 5120.0
        
        return temperature, t_fine
    
    def _compensate_pressure(self, adc: int, t_fine: float) -> float:
        """Compensate raw pressure ADC value."""
        var1 = (t_fine / 2.0) - 64000.0
        var2 = var1 * var1 * (self._cal_data['par_p6'] / 131072.0)
        var2 = var2 + (var1 * self._cal_data['par_p5'] * 2.0)
        var2 = (var2 / 4.0) + (self._cal_data['par_p4'] * 65536.0)
        var1 = ((self._cal_data['par_p3'] * var1 * var1 / 16384.0) + 
                (self._cal_data['par_p2'] * var1)) / 524288.0
        var1 = (1.0 + (var1 / 32768.0)) * self._cal_data['par_p1']
        
        if var1 == 0:
            return 0
        
        pressure = 1048576.0 - adc
        pressure = ((pressure - (var2 / 4096.0)) * 6250.0) / var1
        var1 = (self._cal_data['par_p9'] * pressure * pressure) / 2147483648.0
        var2 = pressure * (self._cal_data['par_p8'] / 32768.0)
        var3 = (pressure / 256.0) ** 3 * (self._cal_data['par_p10'] / 131072.0)
        pressure = pressure + (var1 + var2 + var3 + 
                              (self._cal_data['par_p7'] * 128.0)) / 16.0
        
        return pressure / 100.0  # Convert to hPa
    
    def _compensate_humidity(self, adc: int, t_fine: float) -> float:
        """Compensate raw humidity ADC value."""
        temp_comp = t_fine / 5120.0
        
        var1 = adc - ((self._cal_data['par_h1'] * 16.0) + 
                     ((self._cal_data['par_h3'] / 2.0) * temp_comp))
        var2 = var1 * ((self._cal_data['par_h2'] / 262144.0) * 
                      (1.0 + ((self._cal_data['par_h4'] / 16384.0) * temp_comp) + 
                       ((self._cal_data['par_h5'] / 1048576.0) * temp_comp * temp_comp)))
        var3 = self._cal_data['par_h6'] / 16384.0
        var4 = self._cal_data['par_h7'] / 2097152.0
        humidity = var2 + ((var3 + (var4 * temp_comp)) * var2 * var2)
        
        return max(0.0, min(100.0, humidity))
    
    def _compensate_gas(self, adc: int, gas_range: int) -> float:
        """Compensate raw gas ADC value to resistance in Ohms."""
        # Lookup tables for gas range
        gas_range_lookup1 = [
            1.0, 1.0, 1.0, 1.0, 1.0, 0.99, 1.0, 0.992,
            1.0, 1.0, 0.998, 0.995, 1.0, 0.99, 1.0, 1.0
        ]
        gas_range_lookup2 = [
            8000000.0, 4000000.0, 2000000.0, 1000000.0,
            499500.4995, 248262.1648, 125000.0, 63004.03226,
            31281.28128, 15625.0, 7812.5, 3906.25,
            1953.125, 976.5625, 488.28125, 244.140625
        ]
        
        range_sw_err = self._cal_data['range_sw_err']
        
        var1 = (1340.0 + (5.0 * range_sw_err)) * gas_range_lookup1[gas_range]
        gas_res = var1 * gas_range_lookup2[gas_range] / (adc - 512.0 + var1)
        
        return gas_res
    
    def close(self) -> None:
        """Close I2C connection."""
        self.bus.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

#include <Wire.h>

// BME688 uses either 0x76 or 0x77 depending on SDO wiring.
static const uint8_t BME_ADDR_1 = 0x76;
static const uint8_t BME_ADDR_2 = 0x77;
static const uint8_t BME_CHIP_ID_REG = 0xD0;
static const uint8_t BME_CHIP_ID_EXPECTED = 0x61; // BME680/BME688

uint8_t readRegister(uint8_t deviceAddr, uint8_t reg) {
  Wire.beginTransmission(deviceAddr);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return 0x00;
  }

  if (Wire.requestFrom((int)deviceAddr, 1) != 1) {
    return 0x00;
  }

  return Wire.read();
}

bool deviceResponds(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void scanI2C() {
  Serial.println(F("Scanning I2C bus..."));
  int found = 0;

  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    uint8_t err = Wire.endTransmission();
    if (err == 0) {
      Serial.print(F(" - Device at 0x"));
      if (addr < 16) Serial.print('0');
      Serial.println(addr, HEX);
      found++;
    }
  }

  if (found == 0) {
    Serial.println(F("No I2C devices found."));
  } else {
    Serial.print(F("Scan complete. Devices found: "));
    Serial.println(found);
  }
}

void probeBME688(uint8_t addr) {
  Serial.print(F("Checking 0x"));
  if (addr < 16) Serial.print('0');
  Serial.print(addr, HEX);
  Serial.println(F("..."));

  if (!deviceResponds(addr)) {
    Serial.println(F("  No ACK at this address."));
    return;
  }

  uint8_t chipId = readRegister(addr, BME_CHIP_ID_REG);
  Serial.print(F("  CHIP_ID (0xD0): 0x"));
  if (chipId < 16) Serial.print('0');
  Serial.println(chipId, HEX);

  if (chipId == BME_CHIP_ID_EXPECTED) {
    Serial.println(F("  PASS: BME688 communication looks good."));
  } else {
    Serial.println(F("  Unexpected CHIP_ID. Check wiring, power, pull-ups, or sensor model."));
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for Serial Monitor on boards that need it.
  }

  Wire.begin(); // On MEGA: SDA=20, SCL=21
  delay(100);

  Serial.println();
  Serial.println(F("BME688 I2C communication test (Arduino MEGA)"));
  Serial.println(F("Expected CHIP_ID = 0x61"));
  scanI2C();
  probeBME688(BME_ADDR_1);
  probeBME688(BME_ADDR_2);
}

void loop() {
  delay(3000);
}
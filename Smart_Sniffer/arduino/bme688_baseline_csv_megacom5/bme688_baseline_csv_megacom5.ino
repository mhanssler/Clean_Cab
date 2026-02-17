#include <Arduino.h>
#include <Wire.h>
#include <bme68xLibrary.h>

/*
  BME688 baseline + CSV streamer for Arduino MEGA (I2C)

  Based on Bosch BME68x forced-mode flow used in the Seengreat wiki page.
  The sketch computes a rolling gas-resistance baseline and prints CSV rows
  to Serial so a host app can save training data.
*/

Bme68x bme;

static const uint8_t ADDR_PRIMARY = 0x77;
static const uint8_t ADDR_ALT = 0x76;

static const unsigned long BAUD_RATE = 115200;
static const unsigned long SAMPLE_INTERVAL_MS = 1000;

static const size_t BASELINE_WINDOW = 180;      // 3 minutes @ 1 Hz
static const size_t MIN_BASELINE_SAMPLES = 30;  // minimum before ratio is emitted
static const size_t WARMUP_SAMPLES = 60;        // first 60 seconds as warmup
static const float BASELINE_PERCENTILE = 0.90f; // clean-air estimate
static const float BASELINE_UPDATE_MIN_RATIO = 0.95f; // pause baseline update during odor dips

float gas_window[BASELINE_WINDOW];
size_t gas_count = 0;
size_t gas_head = 0;

float baseline_ohm = 0.0f;
bool baseline_ready = false;
unsigned long sample_index = 0;
uint8_t active_addr = 0x00;

bool initSensorAt(uint8_t addr) {
  bme.begin(addr, Wire);
  int8_t st = bme.checkStatus();
  if (st == BME68X_ERROR) {
    return false;
  }
  active_addr = addr;
  return true;
}

void pushGas(float gas_ohm) {
  gas_window[gas_head] = gas_ohm;
  gas_head = (gas_head + 1) % BASELINE_WINDOW;
  if (gas_count < BASELINE_WINDOW) {
    gas_count++;
  }
}

void sortAscending(float *arr, size_t n) {
  for (size_t i = 1; i < n; i++) {
    float key = arr[i];
    size_t j = i;
    while (j > 0 && arr[j - 1] > key) {
      arr[j] = arr[j - 1];
      j--;
    }
    arr[j] = key;
  }
}

void updateBaseline() {
  if (gas_count < MIN_BASELINE_SAMPLES) {
    baseline_ready = false;
    baseline_ohm = 0.0f;
    return;
  }

  float copy_buf[BASELINE_WINDOW];
  for (size_t i = 0; i < gas_count; i++) {
    copy_buf[i] = gas_window[i];
  }
  sortAscending(copy_buf, gas_count);

  size_t idx = (size_t)((gas_count - 1) * BASELINE_PERCENTILE);
  baseline_ohm = copy_buf[idx];
  baseline_ready = true;
}

const char *phaseName() {
  if (sample_index < WARMUP_SAMPLES) {
    return "WARMUP";
  }
  if (!baseline_ready) {
    return "BASELINE";
  }
  return "LIVE";
}

void setup() {
  Serial.begin(BAUD_RATE);
  while (!Serial) {
    delay(10);
  }

  Wire.begin(); // MEGA I2C pins: SDA=20, SCL=21

  if (!initSensorAt(ADDR_PRIMARY) && !initSensorAt(ADDR_ALT)) {
    Serial.println("# ERROR: BME688 not detected at 0x77 or 0x76");
    while (true) {
      delay(1000);
    }
  }

  // Matches Bosch forced mode example with practical defaults.
  bme.setTPH();
  bme.setHeaterProf(300, 100);

  Serial.print("# INFO: Connected to BME688 at 0x");
  Serial.println(active_addr, HEX);
  Serial.println("# INFO: Baseline uses rolling 90th percentile of gas resistance");
  Serial.println("host_ms,sample,temp_c,pressure_pa,humidity_pct,gas_ohm,baseline_ohm,gas_ratio,gas_delta_pct,phase,status_hex");
}

void loop() {
  unsigned long t0 = millis();
  bme68xData data;

  bme.setOpMode(BME68X_FORCED_MODE);
  delayMicroseconds(bme.getMeasDur());

  if (bme.fetchData()) {
    bme.getData(data);

    float gas_ohm = (float)data.gas_resistance;
    if (!baseline_ready) {
      pushGas(gas_ohm);
      updateBaseline();
    }

    float ratio = 0.0f;
    if (baseline_ready && baseline_ohm > 0.0f) {
      ratio = gas_ohm / baseline_ohm;
      if (ratio >= BASELINE_UPDATE_MIN_RATIO) {
        pushGas(gas_ohm);
        updateBaseline();
      }
    } else {
      pushGas(gas_ohm);
      updateBaseline();
    }
    float delta_pct = (ratio > 0.0f) ? ((ratio - 1.0f) * 100.0f) : 0.0f;

    sample_index++;

    Serial.print(millis());
    Serial.print(",");
    Serial.print(sample_index);
    Serial.print(",");
    Serial.print(data.temperature, 2);
    Serial.print(",");
    Serial.print(data.pressure, 2);
    Serial.print(",");
    Serial.print(data.humidity, 2);
    Serial.print(",");
    Serial.print(gas_ohm, 2);
    Serial.print(",");
    Serial.print(baseline_ohm, 2);
    Serial.print(",");
    Serial.print(ratio, 5);
    Serial.print(",");
    Serial.print(delta_pct, 2);
    Serial.print(",");
    Serial.print(phaseName());
    Serial.print(",");
    Serial.println(data.status, HEX);
  }

  unsigned long elapsed = millis() - t0;
  if (elapsed < SAMPLE_INTERVAL_MS) {
    delay(SAMPLE_INTERVAL_MS - elapsed);
  }
}
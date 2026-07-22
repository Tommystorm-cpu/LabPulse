#include "pressure_monitor.h"

#include <PipeSampleWriter.h>

namespace PressureMonitorFirmware {
namespace {

LabPulse::LinearPressureSensor pressureSensor(PRESSURE_CONFIG);

void emitSample() {
  LabPulse::PipeSampleWriter sample(Serial);
  sample.value(F("pressure"), pressureSensor.read(), PRESSURE_DECIMAL_PLACES);
  sample.end();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
}

void loop() {
  emitSample();
  delay(SAMPLE_INTERVAL_MS);
}

}  // namespace PressureMonitorFirmware

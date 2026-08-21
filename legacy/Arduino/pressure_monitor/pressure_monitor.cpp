#include "pressure_monitor.h"

#include <PipeSampleWriter.h>

namespace PressureMonitorFirmware {
namespace {

// PRESSURE_CONFIG combines the header's pin mapping with its calibration.
LabPulse::LinearPressureSensor pressureSensor(PRESSURE_CONFIG);

void emitSample() {
  // Invalid readings are written as null in the standard pipe format.
  LabPulse::PipeSampleWriter sample(Serial);
  sample.value(PRESSURE.name, pressureSensor.read(), PRESSURE_DECIMAL_PLACES);
  sample.end();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
}

void loop() {
  // A blocking interval is sufficient because this device has no pulse counters.
  emitSample();
  delay(SAMPLE_INTERVAL_MS);
}

}  // namespace PressureMonitorFirmware

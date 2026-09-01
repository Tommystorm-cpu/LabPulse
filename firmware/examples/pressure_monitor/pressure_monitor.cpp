#include "pressure_monitor.h"

#include <PipeSampleWriter.h>

namespace PressureMonitorFirmware {
namespace {

LabPulse::LinearPressureSensor pressureSensor(PRESSURE_CONFIG);
LabPulse::Sht40Sensor environmentSensor(SHT40_CONFIG);

void emitSample() {
  // A failed SHT40 read becomes two null fields without suppressing pressure.
  const LabPulse::Sht40Reading environment = environmentSensor.read();
  LabPulse::PipeSampleWriter sample(Serial);
  sample.value(PRESSURE.name, pressureSensor.read(), PRESSURE_DECIMAL_PLACES);
  sample.value(
      ENVIRONMENT.temperatureName,
      environment.temperature,
      ENVIRONMENT_DECIMAL_PLACES);
  sample.value(
      ENVIRONMENT.humidityName,
      environment.humidity,
      ENVIRONMENT_DECIMAL_PLACES);
  sample.end();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  environmentSensor.begin();
}

void loop() {
  // A blocking interval is sufficient because this device has no pulse counters.
  emitSample();
  delay(SAMPLE_INTERVAL_MS);
}

}  // namespace PressureMonitorFirmware

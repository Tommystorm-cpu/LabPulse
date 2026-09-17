#include "Dht11Sensor.h"

#include <math.h>

namespace LabPulse {
namespace {

Reading validate(float value, float minimum, float maximum) {
  return {value, isfinite(value) && value >= minimum && value <= maximum};
}

}  // namespace

Dht11Sensor::Dht11Sensor(const Dht11Config &config)
    : config_(config), sensor_(config.pin, config.dhtType) {}

void Dht11Sensor::begin() {
  sensor_.begin();
}

Dht11Reading Dht11Sensor::read() {
  const float temperature = sensor_.readTemperature();
  const float humidity = sensor_.readHumidity();
  return {
      validate(
          temperature,
          config_.minimumValidTemperature,
          config_.maximumValidTemperature),
      validate(
          humidity,
          config_.minimumValidHumidity,
          config_.maximumValidHumidity),
  };
}

}  // namespace LabPulse

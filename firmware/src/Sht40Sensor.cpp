#include "Sht40Sensor.h"

#include <math.h>

namespace LabPulse {
namespace {

Reading validate(float value, float minimum, float maximum) {
  return {value, isfinite(value) && value >= minimum && value <= maximum};
}

Sht40Reading invalidReading() {
  return {{0.0F, false}, {0.0F, false}};
}

}  // namespace

Sht40Sensor::Sht40Sensor(const Sht40Config &config)
    : config_(config), initialized_(false) {}

bool Sht40Sensor::begin() {
  initialized_ = sensor_.begin();
  if (initialized_) {
    sensor_.setPrecision(SHT4X_HIGH_PRECISION);
    sensor_.setHeater(SHT4X_NO_HEATER);
  }
  return initialized_;
}

Sht40Reading Sht40Sensor::read() {
  // Retry discovery after startup or a failed transaction so a reconnected
  // sensor can recover without resetting the Arduino.
  if (!initialized_ && !begin()) {
    return invalidReading();
  }

  sensors_event_t humidityEvent;
  sensors_event_t temperatureEvent;
  if (!sensor_.getEvent(&humidityEvent, &temperatureEvent)) {
    initialized_ = false;
    return invalidReading();
  }

  return {
      validate(
          temperatureEvent.temperature,
          config_.minimumValidTemperature,
          config_.maximumValidTemperature),
      validate(
          humidityEvent.relative_humidity,
          config_.minimumValidHumidity,
          config_.maximumValidHumidity),
  };
}

}  // namespace LabPulse

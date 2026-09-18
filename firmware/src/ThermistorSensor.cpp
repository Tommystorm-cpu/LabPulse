#include "ThermistorSensor.h"

#include <math.h>

namespace LabPulse {

ThermistorSensor::ThermistorSensor(const ThermistorConfig &config)
    : config_(config) {}

Reading ThermistorSensor::read() const {
  // Rail values are rejected before conversion; a plausible ADC value alone
  // cannot prove that the sensor and divider are wired correctly.
  const int adc = analogRead(config_.pin);
  if (adc < config_.minimumValidAdc || adc > config_.maximumValidAdc) {
    return {0.0F, false};
  }

  const float voltage =
      adc * (config_.adcReferenceVolts / static_cast<float>(config_.adcDivisor));
  const float fixedResistorVoltage = config_.adcReferenceVolts - voltage;
  if (fixedResistorVoltage <= 0.0F) {
    return {0.0F, false};
  }

  // This divider model puts the thermistor toward ground and the fixed resistor
  // toward the reference supply. Reversing them needs a different conversion.
  const float sensorResistance =
      (voltage / fixedResistorVoltage) * config_.fixedResistanceOhms;
  if (!isfinite(sensorResistance) || sensorResistance <= 0.0F) {
    return {0.0F, false};
  }

  // Coefficients describe this sensor's resistance in ohms. The polynomial is
  // inverse kelvin; subtract 273.15 only after taking its reciprocal.
  const float lnResistance = log(sensorResistance);
  const float denominator =
      config_.steinhartA + config_.steinhartB * lnResistance +
      config_.steinhartC * pow(lnResistance, 2) +
      config_.steinhartD * pow(lnResistance, 3);
  if (!isfinite(denominator) || denominator <= 0.0F) {
    return {0.0F, false};
  }

  const float celsius = (1.0F / denominator) - 273.15F;
  const bool valid = isfinite(celsius) &&
      celsius >= config_.minimumValidCelsius &&
      celsius <= config_.maximumValidCelsius;
  return {celsius, valid};
}

}  // namespace LabPulse

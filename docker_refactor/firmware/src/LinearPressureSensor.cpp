#include "LinearPressureSensor.h"

#include <math.h>

namespace LabPulse {

LinearPressureSensor::LinearPressureSensor(const LinearPressureConfig &config)
    : config_(config) {}

Reading LinearPressureSensor::read() const {
  const int adc = analogRead(config_.pin);
  if (adc < config_.minimumValidAdc || adc > config_.maximumValidAdc) {
    return {0.0F, false};
  }

  const float calibrationSpan =
      config_.maximumCalibrationVolts - config_.minimumCalibrationVolts;
  if (calibrationSpan <= 0.0F || config_.adcDivisor <= 0) {
    return {0.0F, false};
  }

  const float voltage =
      adc * (config_.adcReferenceVolts / static_cast<float>(config_.adcDivisor));
  float basePressure =
      ((voltage - config_.minimumCalibrationVolts) / calibrationSpan) *
      config_.fullScalePressure;
  if (config_.preConversionQuantizationScale > 0.0F) {
    basePressure =
        round(basePressure * config_.preConversionQuantizationScale) /
        config_.preConversionQuantizationScale;
  }

  float output = basePressure * config_.outputMultiplier;
  if (!isfinite(output) || output < config_.minimumValidOutput ||
      output > config_.maximumValidOutput) {
    return {0.0F, false};
  }
  if (config_.clampNegativeToZero && output < 0.0F) {
    output = 0.0F;
  }
  return {output, true};
}

}  // namespace LabPulse

#ifndef LABPULSE_LINEAR_PRESSURE_SENSOR_H
#define LABPULSE_LINEAR_PRESSURE_SENSOR_H

#include <Arduino.h>

#include "Reading.h"

namespace LabPulse {

struct LinearPressureConfig {
  uint8_t pin;
  float adcReferenceVolts;
  int adcDivisor;
  int minimumValidAdc;
  int maximumValidAdc;
  float minimumCalibrationVolts;
  float maximumCalibrationVolts;
  float fullScalePressure;
  float outputMultiplier;
  float preConversionQuantizationScale;
  float minimumValidOutput;
  float maximumValidOutput;
  bool clampNegativeToZero;
};

class LinearPressureSensor {
 public:
  explicit LinearPressureSensor(const LinearPressureConfig &config);

  Reading read() const;

 private:
  LinearPressureConfig config_;
};

}  // namespace LabPulse

#endif

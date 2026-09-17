#ifndef LABPULSE_THERMISTOR_SENSOR_H
#define LABPULSE_THERMISTOR_SENSOR_H

#include <Arduino.h>

#include "Reading.h"

namespace LabPulse {

struct ThermistorConfig {
  uint8_t pin;
  float adcReferenceVolts;
  int adcDivisor;
  int minimumValidAdc;
  int maximumValidAdc;
  float fixedResistanceOhms;
  float steinhartA;
  float steinhartB;
  float steinhartC;
  float steinhartD;
  float minimumValidCelsius;
  float maximumValidCelsius;
};

class ThermistorSensor {
 public:
  explicit ThermistorSensor(const ThermistorConfig &config);

  Reading read() const;

 private:
  ThermistorConfig config_;
};

}  // namespace LabPulse

#endif

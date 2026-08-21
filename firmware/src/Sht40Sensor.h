#ifndef LABPULSE_SHT40_SENSOR_H
#define LABPULSE_SHT40_SENSOR_H

#include <Adafruit_SHT4x.h>
#include <Arduino.h>

#include "Reading.h"

namespace LabPulse {

struct Sht40Config {
  float minimumValidTemperature;
  float maximumValidTemperature;
  float minimumValidHumidity;
  float maximumValidHumidity;
};

struct Sht40Reading {
  Reading temperature;
  Reading humidity;
};

class Sht40Sensor {
 public:
  explicit Sht40Sensor(const Sht40Config &config);

  bool begin();
  Sht40Reading read();

 private:
  Sht40Config config_;
  Adafruit_SHT4x sensor_;
  bool initialized_;
};

}  // namespace LabPulse

#endif

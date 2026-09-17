#ifndef LABPULSE_DHT11_SENSOR_H
#define LABPULSE_DHT11_SENSOR_H

#include <Arduino.h>
#include <DHT.h>

#include "Reading.h"

namespace LabPulse {

struct Dht11Config {
  uint8_t pin;
  uint8_t dhtType;
  float minimumValidTemperature;
  float maximumValidTemperature;
  float minimumValidHumidity;
  float maximumValidHumidity;
};

struct Dht11Reading {
  Reading temperature;
  Reading humidity;
};

class Dht11Sensor {
 public:
  explicit Dht11Sensor(const Dht11Config &config);

  void begin();
  Dht11Reading read();

 private:
  Dht11Config config_;
  DHT sensor_;
};

}  // namespace LabPulse

#endif

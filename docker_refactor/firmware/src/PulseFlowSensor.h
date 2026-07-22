#ifndef LABPULSE_PULSE_FLOW_SENSOR_H
#define LABPULSE_PULSE_FLOW_SENSOR_H

#include <Arduino.h>

#include "Reading.h"

namespace LabPulse {

struct PulseFlowConfig {
  uint8_t pin;
  float pulsesPerLitre;
  uint8_t pinMode;
  int interruptMode;
};

class PulseFlowSensor {
 public:
  explicit PulseFlowSensor(const PulseFlowConfig &config);

  void begin(void (*interruptHandler)());
  void recordPulse();
  Reading sampleAndReset(unsigned long elapsedMilliseconds);

  static void samplePairAndReset(
      PulseFlowSensor &first,
      PulseFlowSensor &second,
      unsigned long elapsedMilliseconds,
      Reading &firstReading,
      Reading &secondReading);

 private:
  Reading readingFor(
      unsigned long pulses,
      unsigned long elapsedMilliseconds) const;

  PulseFlowConfig config_;
  volatile unsigned long pulseCount_;
};

}  // namespace LabPulse

#endif

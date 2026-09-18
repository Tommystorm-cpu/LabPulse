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

  // Register the sketch's tiny interrupt callback, which calls recordPulse().
  void begin(void (*interruptHandler)());
  void recordPulse();
  // Call from the ordinary loop, with interrupts enabled and actual elapsed
  // milliseconds since the previous reset. Returns litres/minute.
  Reading sampleAndReset(unsigned long elapsedMilliseconds);

  // Reset both counters together and write results into the caller's two
  // Reading variables (the & arguments), using one shared elapsed interval.
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
  // An interrupt changes this outside normal execution. volatile forces real
  // reads/writes; the sampling code still needs interrupts off for a safe copy.
  volatile unsigned long pulseCount_;
};

}  // namespace LabPulse

#endif

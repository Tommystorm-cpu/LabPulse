#include "PulseFlowSensor.h"

#include <math.h>

namespace LabPulse {

PulseFlowSensor::PulseFlowSensor(const PulseFlowConfig &config)
    : config_(config), pulseCount_(0) {}

void PulseFlowSensor::begin(void (*interruptHandler)()) {
  pinMode(config_.pin, config_.pinMode);
  attachInterrupt(
      digitalPinToInterrupt(config_.pin), interruptHandler, config_.interruptMode);
}

void PulseFlowSensor::recordPulse() {
  // Keep interrupt work short: no serial output or conversion calculations here.
  ++pulseCount_;
}

Reading PulseFlowSensor::readingFor(
    unsigned long pulses,
    unsigned long elapsedMilliseconds) const {
  if (elapsedMilliseconds == 0 || config_.pulsesPerLitre <= 0.0F) {
    return {0.0F, false};
  }
  const float litresPerMinute =
      // 60000 converts the measured millisecond interval into minutes.
      (pulses * 60000.0F) /
      (config_.pulsesPerLitre * static_cast<float>(elapsedMilliseconds));
  return {litresPerMinute, isfinite(litresPerMinute)};
}

Reading PulseFlowSensor::sampleAndReset(unsigned long elapsedMilliseconds) {
  // On the Uno, copying this multi-byte counter can be interrupted midway.
  // Copy/reset together, then re-enable interrupts before doing arithmetic.
  noInterrupts();
  const unsigned long pulses = pulseCount_;
  pulseCount_ = 0;
  interrupts();
  return readingFor(pulses, elapsedMilliseconds);
}

void PulseFlowSensor::samplePairAndReset(
    PulseFlowSensor &first,
    PulseFlowSensor &second,
    unsigned long elapsedMilliseconds,
    Reading &firstReading,
    Reading &secondReading) {
  // One short interruption keeps the two counters on the same reset boundary.
  // These sampling methods assume interrupts were enabled on entry.
  noInterrupts();
  const unsigned long firstPulses = first.pulseCount_;
  const unsigned long secondPulses = second.pulseCount_;
  first.pulseCount_ = 0;
  second.pulseCount_ = 0;
  interrupts();

  firstReading = first.readingFor(firstPulses, elapsedMilliseconds);
  secondReading = second.readingFor(secondPulses, elapsedMilliseconds);
}

}  // namespace LabPulse

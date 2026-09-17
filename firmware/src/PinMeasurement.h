#ifndef LABPULSE_PIN_MEASUREMENT_H
#define LABPULSE_PIN_MEASUREMENT_H

#include <Arduino.h>

namespace LabPulse {

// Connects one physical Arduino input to the name emitted over serial.
// Device firmware declares these records in its configuration header.
struct PinMeasurement {
  uint8_t pin;
  const char *name;
};

}  // namespace LabPulse

#endif

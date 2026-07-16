#ifndef LABPULSE_PROTOCOL_H
#define LABPULSE_PROTOCOL_H

#include <Arduino.h>

namespace LabPulseProtocol {

constexpr uint8_t SCHEMA_VERSION = 1;
constexpr float ADC_REFERENCE_VOLTS = 5.0F;
constexpr int ADC_MAX = 1023;

struct ThermistorReading {
  int adc;
  float celsius;
  bool valid;
};

bool finiteInRange(float value, float minimum, float maximum);

ThermistorReading readGe1337(
    uint8_t pin,
    float fixedResistanceOhms = 4700.0F);

void printFloatOrNull(float value, bool valid, uint8_t digits);

void printHello(
    const __FlashStringHelper *device,
    const __FlashStringHelper *firmware);

void printSampleStart(
    const __FlashStringHelper *device,
    const __FlashStringHelper *firmware,
    unsigned long uptimeMs);

}  // namespace LabPulseProtocol

#endif


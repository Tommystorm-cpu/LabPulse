#include "LabPulseProtocol.h"

#include <math.h>

namespace LabPulseProtocol {

namespace {

constexpr float STEINHART_A = 0.0014948F;
constexpr float STEINHART_B = 0.00021902F;
constexpr float STEINHART_C = 1.6239e-6F;
constexpr float STEINHART_D = 3.4445e-8F;
constexpr int ADC_VALID_MIN = 2;
constexpr int ADC_VALID_MAX = ADC_MAX - 2;
constexpr float TEMPERATURE_VALID_MIN_C = -100.0F;
constexpr float TEMPERATURE_VALID_MAX_C = 200.0F;

void printEnvelopeStart(
    const __FlashStringHelper *device,
    const __FlashStringHelper *firmware) {
  Serial.print(F("{\"device\":\""));
  Serial.print(device);
  Serial.print(F("\",\"schema\":"));
  Serial.print(SCHEMA_VERSION);
  Serial.print(F(",\"firmware\":\""));
  Serial.print(firmware);
  Serial.print(F("\""));
}

}  // namespace

bool finiteInRange(float value, float minimum, float maximum) {
  return isfinite(value) && value >= minimum && value <= maximum;
}

ThermistorMeasurement readGe1337(uint8_t pin, float fixedResistanceOhms) {
  ThermistorMeasurement measurement = {analogRead(pin), 0.0F, false};
  if (measurement.adc < ADC_VALID_MIN || measurement.adc > ADC_VALID_MAX) {
    return measurement;
  }

  const float voltage =
      measurement.adc * (ADC_REFERENCE_VOLTS / static_cast<float>(ADC_MAX));
  const float fixedResistorVoltage = ADC_REFERENCE_VOLTS - voltage;
  if (fixedResistorVoltage <= 0.0F) {
    return measurement;
  }

  const float sensorResistance =
      (voltage / fixedResistorVoltage) * fixedResistanceOhms;
  if (!isfinite(sensorResistance) || sensorResistance <= 0.0F) {
    return measurement;
  }

  const float lnResistance = log(sensorResistance);
  const float denominator =
      STEINHART_A + STEINHART_B * lnResistance +
      STEINHART_C * pow(lnResistance, 2) +
      STEINHART_D * pow(lnResistance, 3);
  if (!isfinite(denominator) || denominator <= 0.0F) {
    return measurement;
  }

  measurement.celsius = (1.0F / denominator) - 273.15F;
  measurement.valid = finiteInRange(
      measurement.celsius,
      TEMPERATURE_VALID_MIN_C,
      TEMPERATURE_VALID_MAX_C);
  return measurement;
}

void printFloatOrNull(float value, bool valid, uint8_t digits) {
  if (valid && isfinite(value)) {
    Serial.print(value, digits);
  } else {
    Serial.print(F("null"));
  }
}

void printHello(
    const __FlashStringHelper *device,
    const __FlashStringHelper *firmware) {
  printEnvelopeStart(device, firmware);
  Serial.println(F(",\"type\":\"hello\"}"));
}

void printSampleStart(
    const __FlashStringHelper *device,
    const __FlashStringHelper *firmware,
    unsigned long uptimeMs) {
  printEnvelopeStart(device, firmware);
  Serial.print(F(",\"type\":\"sample\",\"uptime_ms\":"));
  Serial.print(uptimeMs);
  Serial.print(F(",\"measurements\":{"));
}

}  // namespace LabPulseProtocol


#include <Arduino.h>
#include <math.h>

namespace {

constexpr unsigned long SAMPLE_INTERVAL_MS = 1000UL;
constexpr uint8_t PRESSURE_PIN = A0;
constexpr float ADC_REFERENCE_VOLTS = 5.0F;
constexpr int ADC_MAX = 1023;

// Preserve the installed pressure firmware's calibration values.
constexpr float START_VOLTS = 0.48F;
constexpr float END_VOLTS = 4.5F;
constexpr float MAX_PRESSURE_MPA = 1.6F;
constexpr float PRESSURE_MIN_VALID_BAR = -0.25F;
constexpr float PRESSURE_MAX_VALID_BAR = 16.5F;

void emitSample() {
  const int pressureAdc = analogRead(PRESSURE_PIN);
  const bool adcValid = pressureAdc >= 2 && pressureAdc <= ADC_MAX - 2;
  const float voltage = pressureAdc * (ADC_REFERENCE_VOLTS / ADC_MAX);
  const float voltsPerMpa = (END_VOLTS - START_VOLTS) / MAX_PRESSURE_MPA;
  const float pressureMpa = (voltage - START_VOLTS) / voltsPerMpa;
  // Preserve the old sketch's four-decimal MPa serial quantisation before
  // doing the conversion that previously lived in Python.
  const float legacyPressureMpa = round(pressureMpa * 10000.0F) / 10000.0F;
  const float pressureBar = legacyPressureMpa * 10.0F;
  const bool pressureValid = adcValid && isfinite(pressureBar) &&
      pressureBar >= PRESSURE_MIN_VALID_BAR &&
      pressureBar <= PRESSURE_MAX_VALID_BAR;

  Serial.print(F("pressure: "));
  if (pressureValid) {
    // The legacy pipeline converted MPa to bar in Python and published 2 decimals.
    Serial.println(pressureBar, 2);
  } else {
    Serial.println(F("null"));
  }
}

}  // namespace

void setup() {
  Serial.begin(9600);
}

void loop() {
  emitSample();
  delay(SAMPLE_INTERVAL_MS);
}

#include <Arduino.h>
#include <LabPulseProtocol.h>

namespace {

constexpr unsigned long SAMPLE_INTERVAL_MS = 1000UL;
constexpr uint8_t PRESSURE_PIN = A0;
constexpr float START_VOLTS = 0.48F;
constexpr float END_VOLTS = 4.5F;
constexpr float MAX_PRESSURE_MPA = 1.6F;
constexpr float PRESSURE_MIN_VALID_BAR = -0.25F;
constexpr float PRESSURE_MAX_VALID_BAR = 16.5F;

unsigned long lastSampleMs = 0;

void emitSample(unsigned long now) {
  const int pressureAdc = analogRead(PRESSURE_PIN);
  const float voltage = pressureAdc *
      (LabPulseProtocol::ADC_REFERENCE_VOLTS /
       static_cast<float>(LabPulseProtocol::ADC_MAX));
  const float voltsPerMpa = (END_VOLTS - START_VOLTS) / MAX_PRESSURE_MPA;
  float pressureBar = ((voltage - START_VOLTS) / voltsPerMpa) * 10.0F;
  const bool adcValid = pressureAdc >= 2 &&
      pressureAdc <= LabPulseProtocol::ADC_MAX - 2;
  bool pressureValid = adcValid && LabPulseProtocol::finiteInRange(
      pressureBar,
      PRESSURE_MIN_VALID_BAR,
      PRESSURE_MAX_VALID_BAR);
  if (pressureValid && pressureBar < 0.0F) {
    pressureBar = 0.0F;
  }

  LabPulseProtocol::printSampleStart(
      F("pressure_monitor"), F("pressure-monitor-1.0.0"), now);
  Serial.print(F("\"pressure\":"));
  LabPulseProtocol::printFloatOrNull(pressureBar, pressureValid, 3);
  Serial.print(F("},\"diagnostics\":{\"pressure_adc\":"));
  Serial.print(pressureAdc);
  Serial.println(F("}}"));
}

}  // namespace

void setup() {
  Serial.begin(9600);
  LabPulseProtocol::printHello(
      F("pressure_monitor"), F("pressure-monitor-1.0.0"));
}

void loop() {
  const unsigned long now = millis();
  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMs = now;
  emitSample(now);
}


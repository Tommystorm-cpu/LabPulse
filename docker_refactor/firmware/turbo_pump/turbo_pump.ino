#include <Arduino.h>
#include <math.h>

namespace {

constexpr unsigned long SAMPLE_INTERVAL_MS = 5000UL;
constexpr float ADC_REFERENCE_VOLTS = 5.0F;
constexpr int ADC_MAX = 1023;

constexpr uint8_t FLOW1_PIN = 2;
constexpr uint8_t FLOW2_PIN = 3;
constexpr float FLOW_PULSES_PER_LITRE = 450.0F;

constexpr uint8_t TEMPERATURE_PINS[] = {A0, A1, A2, A3};
constexpr float FIXED_RESISTANCE_OHMS = 4700.0F;
constexpr float STEINHART_A = 0.0014948F;
constexpr float STEINHART_B = 0.00021902F;
constexpr float STEINHART_C = 1.6239e-6F;
constexpr float STEINHART_D = 3.4445e-8F;

volatile unsigned long flow1PulseCount = 0;
volatile unsigned long flow2PulseCount = 0;
unsigned long lastSampleMs = 0;

struct Reading {
  float value;
  bool valid;
};

void countFlow1Pulse() {
  ++flow1PulseCount;
}

void countFlow2Pulse() {
  ++flow2PulseCount;
}

float flowLitresPerMinute(unsigned long pulses, unsigned long elapsedMs) {
  if (elapsedMs == 0) {
    return 0.0F;
  }
  return (pulses * 60000.0F) /
      (FLOW_PULSES_PER_LITRE * static_cast<float>(elapsedMs));
}

Reading readTemperature(uint8_t pin) {
  const int adc = analogRead(pin);
  if (adc < 2 || adc > ADC_MAX - 2) {
    return {0.0F, false};
  }

  const float voltage = adc * (ADC_REFERENCE_VOLTS / ADC_MAX);
  const float fixedResistorVoltage = ADC_REFERENCE_VOLTS - voltage;
  const float sensorResistance =
      (voltage / fixedResistorVoltage) * FIXED_RESISTANCE_OHMS;
  const float lnResistance = log(sensorResistance);
  const float temperature =
      (1.0F /
       (STEINHART_A + STEINHART_B * lnResistance +
        STEINHART_C * pow(lnResistance, 2) +
        STEINHART_D * pow(lnResistance, 3))) -
      273.15F;
  const bool valid =
      isfinite(temperature) && temperature >= -100.0F && temperature <= 200.0F;
  return {temperature, valid};
}

void printValue(float value, bool valid, uint8_t digits) {
  if (valid && isfinite(value)) {
    Serial.print(value, digits);
  } else {
    Serial.print(F("null"));
  }
}

void emitSample(unsigned long elapsedMs) {
  unsigned long flow1Pulses;
  unsigned long flow2Pulses;
  noInterrupts();
  flow1Pulses = flow1PulseCount;
  flow2Pulses = flow2PulseCount;
  flow1PulseCount = 0;
  flow2PulseCount = 0;
  interrupts();

  Serial.print(F("flow1: "));
  printValue(flowLitresPerMinute(flow1Pulses, elapsedMs), true, 2);
  Serial.print(F(" | flow2: "));
  printValue(flowLitresPerMinute(flow2Pulses, elapsedMs), true, 2);
  for (uint8_t index = 0; index < 4; ++index) {
    const Reading temperature = readTemperature(TEMPERATURE_PINS[index]);
    Serial.print(F(" | temp"));
    Serial.print(index);
    Serial.print(F(": "));
    printValue(temperature.value, temperature.valid, 2);
  }
  Serial.println();
}

}  // namespace

void setup() {
  Serial.begin(9600);
  pinMode(FLOW1_PIN, INPUT_PULLUP);
  pinMode(FLOW2_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FLOW1_PIN), countFlow1Pulse, FALLING);
  attachInterrupt(digitalPinToInterrupt(FLOW2_PIN), countFlow2Pulse, FALLING);
}

void loop() {
  const unsigned long now = millis();
  const unsigned long elapsedMs = now - lastSampleMs;
  if (elapsedMs < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMs = now;
  emitSample(elapsedMs);
}

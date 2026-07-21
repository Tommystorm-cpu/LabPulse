#include <Arduino.h>
#include <DHT.h>
#include <math.h>

namespace {

constexpr unsigned long SAMPLE_INTERVAL_MS = 5000UL;
constexpr float ADC_REFERENCE_VOLTS = 5.0F;
constexpr int ADC_MAX = 1023;

constexpr uint8_t FLOW1_PIN = 3;
constexpr uint8_t FLOW2_PIN = 2;
constexpr float FLOW_PULSES_PER_LITRE = 450.0F;

constexpr uint8_t TEMPERATURE_PINS[] = {A0, A1, A2, A3};
constexpr float FIXED_RESISTANCE_OHMS = 4700.0F;
constexpr float STEINHART_A = 0.0014948F;
constexpr float STEINHART_B = 0.00021902F;
constexpr float STEINHART_C = 1.6239e-6F;
constexpr float STEINHART_D = 3.4445e-8F;

constexpr uint8_t DHT_PIN = 4;
constexpr uint8_t PRESSURE1_PIN = A5;
constexpr uint8_t PRESSURE2_PIN = A4;
constexpr float PRESSURE_MAX_MPA = 1.6F;

DHT roomSensor(DHT_PIN, DHT11);
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

bool finiteInRange(float value, float minimum, float maximum) {
  return isfinite(value) && value >= minimum && value <= maximum;
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
  return {temperature, finiteInRange(temperature, -100.0F, 200.0F)};
}

Reading readPressure(uint8_t pin) {
  const int adc = analogRead(pin);
  if (adc < 2 || adc > ADC_MAX - 2) {
    return {0.0F, false};
  }

  // Keep the installed pump-room firmware's 5.0 / 1024.0 ADC scaling.
  const float voltage = adc * (ADC_REFERENCE_VOLTS / 1024.0F);
  float pressureBar =
      (((voltage - 0.5F) / 4.0F) * PRESSURE_MAX_MPA) * 10.0F;
  if (!finiteInRange(pressureBar, -0.25F, 16.5F)) {
    return {0.0F, false};
  }
  if (pressureBar < 0.0F) {
    pressureBar = 0.0F;
  }
  return {pressureBar, true};
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

  const float flow1 = flowLitresPerMinute(flow1Pulses, elapsedMs);
  const float flow2 = flowLitresPerMinute(flow2Pulses, elapsedMs);
  Reading temperatures[4];
  for (uint8_t index = 0; index < 4; ++index) {
    temperatures[index] = readTemperature(TEMPERATURE_PINS[index]);
  }

  const float roomTemperature = roomSensor.readTemperature();
  const float roomHumidity = roomSensor.readHumidity();
  const Reading pressure1 = readPressure(PRESSURE1_PIN);
  const Reading pressure2 = readPressure(PRESSURE2_PIN);

  Serial.print(F("flow1: "));
  printValue(flow1, true, 2);
  Serial.print(F(" | flow2: "));
  printValue(flow2, true, 2);
  for (uint8_t index = 0; index < 4; ++index) {
    Serial.print(F(" | temp"));
    Serial.print(index);
    Serial.print(F(": "));
    printValue(temperatures[index].value, temperatures[index].valid, 2);
  }
  Serial.print(F(" | roomtemp: "));
  printValue(roomTemperature, finiteInRange(roomTemperature, -40.0F, 80.0F), 1);
  Serial.print(F(" | roomhum: "));
  printValue(roomHumidity, finiteInRange(roomHumidity, 0.0F, 100.0F), 1);
  Serial.print(F(" | press1: "));
  printValue(pressure1.value, pressure1.valid, 2);
  Serial.print(F(" | press2: "));
  printValue(pressure2.value, pressure2.valid, 2);
  Serial.println();
}

}  // namespace

void setup() {
  Serial.begin(9600);
  roomSensor.begin();
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

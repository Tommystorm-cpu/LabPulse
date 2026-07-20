#include <Arduino.h>
#include <DHT.h>
#include <LabPulseProtocol.h>

namespace {

constexpr unsigned long SAMPLE_INTERVAL_MS = 5000UL;
constexpr float FLOW_PULSES_PER_LITRE = 450.0F;
constexpr uint8_t FLOW1_PIN = 3;
constexpr uint8_t FLOW2_PIN = 2;
constexpr uint8_t DHT_PIN = 4;
constexpr uint8_t PRESSURE1_PIN = A5;
constexpr uint8_t PRESSURE2_PIN = A4;
constexpr uint8_t TEMPERATURE_PINS[] = {A0, A1, A2, A3};
constexpr float PRESSURE_MAX_MPA = 1.6F;

DHT roomSensor(DHT_PIN, DHT11);
volatile unsigned long flow1PulseCount = 0;
volatile unsigned long flow2PulseCount = 0;
unsigned long lastSampleMs = 0;

struct PressureMeasurement {
  int adc;
  float bar;
  bool valid;
};

void countFlow1Pulse() {
  ++flow1PulseCount;
}

void countFlow2Pulse() {
  ++flow2PulseCount;
}

float flowLitresPerMinute(unsigned long pulses, unsigned long elapsedMs) {
  if (elapsedMs == 0 || FLOW_PULSES_PER_LITRE <= 0.0F) {
    return 0.0F;
  }
  return (pulses * 60000.0F) /
      (FLOW_PULSES_PER_LITRE * static_cast<float>(elapsedMs));
}

PressureMeasurement readPressure(uint8_t pin) {
  PressureMeasurement measurement = {analogRead(pin), 0.0F, false};
  if (measurement.adc < 2 || measurement.adc > LabPulseProtocol::ADC_MAX - 2) {
    return measurement;
  }
  const float voltage = measurement.adc *
      (LabPulseProtocol::ADC_REFERENCE_VOLTS /
       static_cast<float>(LabPulseProtocol::ADC_MAX));
  measurement.bar = (((voltage - 0.5F) / 4.0F) * PRESSURE_MAX_MPA) * 10.0F;
  measurement.valid = LabPulseProtocol::finiteInRange(measurement.bar, -0.25F, 16.5F);
  if (measurement.valid && measurement.bar < 0.0F) {
    measurement.bar = 0.0F;
  }
  return measurement;
}

void emitSample(unsigned long now, unsigned long elapsedMs) {
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
  LabPulseProtocol::ThermistorMeasurement temperatures[4];
  for (uint8_t index = 0; index < 4; ++index) {
    temperatures[index] =
        LabPulseProtocol::readGe1337(TEMPERATURE_PINS[index]);
  }

  const float roomTemperature = roomSensor.readTemperature();
  const float roomHumidity = roomSensor.readHumidity();
  const bool roomTemperatureValid =
      LabPulseProtocol::finiteInRange(roomTemperature, -40.0F, 80.0F);
  const bool roomHumidityValid =
      LabPulseProtocol::finiteInRange(roomHumidity, 0.0F, 100.0F);
  const PressureMeasurement pressure1 = readPressure(PRESSURE1_PIN);
  const PressureMeasurement pressure2 = readPressure(PRESSURE2_PIN);

  LabPulseProtocol::printSampleStart(
      F("pump_room"), F("pump-room-1.0.0"), now);
  Serial.print(F("\"flow1\":"));
  LabPulseProtocol::printFloatOrNull(flow1, true, 3);
  Serial.print(F(",\"flow2\":"));
  LabPulseProtocol::printFloatOrNull(flow2, true, 3);
  for (uint8_t index = 0; index < 4; ++index) {
    Serial.print(F(",\"temp"));
    Serial.print(index);
    Serial.print(F("\":"));
    LabPulseProtocol::printFloatOrNull(
        temperatures[index].celsius,
        temperatures[index].valid,
        2);
  }
  Serial.print(F(",\"roomtemp\":"));
  LabPulseProtocol::printFloatOrNull(
      roomTemperature, roomTemperatureValid, 1);
  Serial.print(F(",\"roomhum\":"));
  LabPulseProtocol::printFloatOrNull(roomHumidity, roomHumidityValid, 1);
  Serial.print(F(",\"press1\":"));
  LabPulseProtocol::printFloatOrNull(pressure1.bar, pressure1.valid, 3);
  Serial.print(F(",\"press2\":"));
  LabPulseProtocol::printFloatOrNull(pressure2.bar, pressure2.valid, 3);

  Serial.print(F("},\"diagnostics\":{\"sample_ms\":"));
  Serial.print(elapsedMs);
  Serial.print(F(",\"flow1_pulses\":"));
  Serial.print(flow1Pulses);
  Serial.print(F(",\"flow2_pulses\":"));
  Serial.print(flow2Pulses);
  for (uint8_t index = 0; index < 4; ++index) {
    Serial.print(F(",\"temp"));
    Serial.print(index);
    Serial.print(F("_adc\":"));
    Serial.print(temperatures[index].adc);
  }
  Serial.print(F(",\"press1_adc\":"));
  Serial.print(pressure1.adc);
  Serial.print(F(",\"press2_adc\":"));
  Serial.print(pressure2.adc);
  Serial.println(F("}}"));
}

}  // namespace

void setup() {
  Serial.begin(9600);
  roomSensor.begin();
  pinMode(FLOW1_PIN, INPUT_PULLUP);
  pinMode(FLOW2_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FLOW1_PIN), countFlow1Pulse, FALLING);
  attachInterrupt(digitalPinToInterrupt(FLOW2_PIN), countFlow2Pulse, FALLING);
  LabPulseProtocol::printHello(F("pump_room"), F("pump-room-1.0.0"));
}

void loop() {
  const unsigned long now = millis();
  const unsigned long elapsedMs = now - lastSampleMs;
  if (elapsedMs < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMs = now;
  emitSample(now, elapsedMs);
}


#include "pump_room.h"

#include <PipeSampleWriter.h>

namespace PumpRoomFirmware {
namespace {

// Sensor objects use the pin mappings and calibration from pump_room.h.
LabPulse::PulseFlowSensor flow1(FLOW1_CONFIG);
LabPulse::PulseFlowSensor flow2(FLOW2_CONFIG);

// Temperature sensor and mapping arrays share the same indexes.
LabPulse::ThermistorSensor temperatures[] = {
    LabPulse::ThermistorSensor(TEMPERATURE_CONFIGS[0]),
    LabPulse::ThermistorSensor(TEMPERATURE_CONFIGS[1]),
    LabPulse::ThermistorSensor(TEMPERATURE_CONFIGS[2]),
    LabPulse::ThermistorSensor(TEMPERATURE_CONFIGS[3]),
};

LabPulse::Dht11Sensor dht11Sensor(DHT11_CONFIG);
LabPulse::LinearPressureSensor pressure1(PRESSURE1_CONFIG);
LabPulse::LinearPressureSensor pressure2(PRESSURE2_CONFIG);

unsigned long lastSampleMilliseconds = 0;

// Interrupt handlers only record pulses; calculations happen during sampling.
void countFlow1Pulse() {
  flow1.recordPulse();
}

void countFlow2Pulse() {
  flow2.recordPulse();
}

void emitSample(unsigned long elapsedMilliseconds) {
  // Sample both pulse counters atomically over the same elapsed interval.
  LabPulse::Reading flow1Reading;
  LabPulse::Reading flow2Reading;
  LabPulse::PulseFlowSensor::samplePairAndReset(
      flow1, flow2, elapsedMilliseconds, flow1Reading, flow2Reading);

  // One DHT11 read returns both temperature and humidity.
  const LabPulse::Dht11Reading roomReading = dht11Sensor.read();

  // Write one complete sample using measurement names from pump_room.h.
  LabPulse::PipeSampleWriter sample(Serial);
  sample.value(FLOW1.name, flow1Reading, FLOW_DECIMAL_PLACES);
  sample.value(FLOW2.name, flow2Reading, FLOW_DECIMAL_PLACES);

  sample.value(
      TEMPERATURES[0].name,
      temperatures[0].read(),
      TEMPERATURE_DECIMAL_PLACES);
  sample.value(
      TEMPERATURES[1].name,
      temperatures[1].read(),
      TEMPERATURE_DECIMAL_PLACES);
  sample.value(
      TEMPERATURES[2].name,
      temperatures[2].read(),
      TEMPERATURE_DECIMAL_PLACES);
  sample.value(
      TEMPERATURES[3].name,
      temperatures[3].read(),
      TEMPERATURE_DECIMAL_PLACES);

  sample.value(
      ROOM_DHT11.temperatureName,
      roomReading.temperature,
      ROOM_DECIMAL_PLACES);
  sample.value(
      ROOM_DHT11.humidityName,
      roomReading.humidity,
      ROOM_DECIMAL_PLACES);

  sample.value(PRESSURES[0].name, pressure1.read(), PRESSURE_DECIMAL_PLACES);
  sample.value(PRESSURES[1].name, pressure2.read(), PRESSURE_DECIMAL_PLACES);
  sample.end();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  dht11Sensor.begin();
  flow1.begin(countFlow1Pulse);
  flow2.begin(countFlow2Pulse);
}

void loop() {
  // Non-blocking timing keeps the flow interrupts active between samples.
  const unsigned long now = millis();
  const unsigned long elapsedMilliseconds = now - lastSampleMilliseconds;
  if (elapsedMilliseconds < SAMPLE_INTERVAL_MS) {
    return;
  }

  lastSampleMilliseconds = now;
  emitSample(elapsedMilliseconds);
}

}  // namespace PumpRoomFirmware

#include "turbo_pump.h"

#include <PipeSampleWriter.h>

namespace TurboPumpFirmware {
namespace {

LabPulse::PulseFlowSensor flow1(FLOW1_CONFIG);
LabPulse::PulseFlowSensor flow2(FLOW2_CONFIG);
LabPulse::ThermistorSensor temperatures[] = {
    LabPulse::ThermistorSensor(TEMPERATURE_CONFIGS[0]),
    LabPulse::ThermistorSensor(TEMPERATURE_CONFIGS[1]),
    LabPulse::ThermistorSensor(TEMPERATURE_CONFIGS[2]),
    LabPulse::ThermistorSensor(TEMPERATURE_CONFIGS[3]),
};
unsigned long lastSampleMilliseconds = 0;

void countFlow1Pulse() {
  flow1.recordPulse();
}

void countFlow2Pulse() {
  flow2.recordPulse();
}

void emitSample(unsigned long elapsedMilliseconds) {
  LabPulse::Reading flow1Reading;
  LabPulse::Reading flow2Reading;
  LabPulse::PulseFlowSensor::samplePairAndReset(
      flow1, flow2, elapsedMilliseconds, flow1Reading, flow2Reading);

  LabPulse::PipeSampleWriter sample(Serial);
  sample.value(F("flow1"), flow1Reading, FLOW_DECIMAL_PLACES);
  sample.value(F("flow2"), flow2Reading, FLOW_DECIMAL_PLACES);
  sample.value(F("temp0"), temperatures[0].read(), TEMPERATURE_DECIMAL_PLACES);
  sample.value(F("temp1"), temperatures[1].read(), TEMPERATURE_DECIMAL_PLACES);
  sample.value(F("temp2"), temperatures[2].read(), TEMPERATURE_DECIMAL_PLACES);
  sample.value(F("temp3"), temperatures[3].read(), TEMPERATURE_DECIMAL_PLACES);
  sample.end();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  flow1.begin(countFlow1Pulse);
  flow2.begin(countFlow2Pulse);
}

void loop() {
  const unsigned long now = millis();
  const unsigned long elapsedMilliseconds = now - lastSampleMilliseconds;
  if (elapsedMilliseconds < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMilliseconds = now;
  emitSample(elapsedMilliseconds);
}

}  // namespace TurboPumpFirmware

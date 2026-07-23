#ifndef LABPULSE_PUMP_ROOM_FIRMWARE_H
#define LABPULSE_PUMP_ROOM_FIRMWARE_H

#include <Arduino.h>
#include <Dht11Sensor.h>
#include <LinearPressureSensor.h>
#include <PinMeasurement.h>
#include <PulseFlowSensor.h>
#include <ThermistorSensor.h>

namespace PumpRoomFirmware {

constexpr unsigned long SAMPLE_INTERVAL_MS = 5000UL;
constexpr uint16_t SERIAL_BAUD_RATE = 9600;
constexpr uint8_t FLOW_DECIMAL_PLACES = 2;
constexpr uint8_t TEMPERATURE_DECIMAL_PLACES = 2;
constexpr uint8_t ROOM_DECIMAL_PLACES = 1;
constexpr uint8_t PRESSURE_DECIMAL_PLACES = 2;

// Authoritative pin-to-name mappings. Each record is {Arduino pin, serial
// measurement name}. Editing a record changes both the sensor input used by
// the firmware and the name written to the pipe-delimited serial sample.
constexpr LabPulse::PinMeasurement FLOW1 = {3, "flow1"};
constexpr LabPulse::PinMeasurement FLOW2 = {2, "flow2"};
constexpr LabPulse::PinMeasurement TEMPERATURES[] = {
    {A0, "temp0"},
    {A1, "temp1"},
    {A2, "temp2"},
    {A3, "temp3"},
};

// A DHT11 has one data pin but produces two named measurements, so its mapping
// keeps the shared pin and both output names together in one record.
struct Dht11Measurements {
  uint8_t pin;
  const char *temperatureName;
  const char *humidityName;
};
constexpr Dht11Measurements ROOM_DHT11 = {4, "roomtemp", "roomhum"};

constexpr LabPulse::PinMeasurement PRESSURES[] = {
    {A5, "press1"},
    {A4, "press2"},
};

// Flow configuration retained from the current pump-room firmware.
constexpr LabPulse::PulseFlowConfig FLOW1_CONFIG = {
    FLOW1.pin, 450.0F, INPUT_PULLUP, FALLING};
constexpr LabPulse::PulseFlowConfig FLOW2_CONFIG = {
    FLOW2.pin, 450.0F, INPUT_PULLUP, FALLING};

// Water-temperature configuration retained from the current firmware.
constexpr LabPulse::ThermistorConfig TEMPERATURE_CONFIGS[] = {
    {TEMPERATURES[0].pin, 5.0F, 1023, 2, 1021, 4700.0F, 0.0014948F, 0.00021902F,
     1.6239e-6F, 3.4445e-8F, -100.0F, 200.0F},
    {TEMPERATURES[1].pin, 5.0F, 1023, 2, 1021, 4700.0F, 0.0014948F, 0.00021902F,
     1.6239e-6F, 3.4445e-8F, -100.0F, 200.0F},
    {TEMPERATURES[2].pin, 5.0F, 1023, 2, 1021, 4700.0F, 0.0014948F, 0.00021902F,
     1.6239e-6F, 3.4445e-8F, -100.0F, 200.0F},
    {TEMPERATURES[3].pin, 5.0F, 1023, 2, 1021, 4700.0F, 0.0014948F, 0.00021902F,
     1.6239e-6F, 3.4445e-8F, -100.0F, 200.0F},
};

// DHT11 configuration retained from the current pump-room firmware.
constexpr LabPulse::Dht11Config DHT11_CONFIG = {
    ROOM_DHT11.pin, DHT11, -40.0F, 80.0F, 0.0F, 100.0F};

// The pump-room transducers use the legacy 5.0 / 1024.0 ADC scaling and clamp.
constexpr LabPulse::LinearPressureConfig PRESSURE1_CONFIG = {
    PRESSURES[0].pin, 5.0F, 1024, 2, 1021, 0.5F, 4.5F, 1.6F, 10.0F, 0.0F,
    -0.25F, 16.5F, true};
constexpr LabPulse::LinearPressureConfig PRESSURE2_CONFIG = {
    PRESSURES[1].pin, 5.0F, 1024, 2, 1021, 0.5F, 4.5F, 1.6F, 10.0F, 0.0F,
    -0.25F, 16.5F, true};

void setup();
void loop();

}  // namespace PumpRoomFirmware

#endif

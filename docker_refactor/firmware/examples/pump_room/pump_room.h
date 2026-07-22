#ifndef LABPULSE_PUMP_ROOM_FIRMWARE_H
#define LABPULSE_PUMP_ROOM_FIRMWARE_H

#include <Arduino.h>
#include <Dht11Sensor.h>
#include <LinearPressureSensor.h>
#include <PulseFlowSensor.h>
#include <ThermistorSensor.h>

namespace PumpRoomFirmware {

constexpr unsigned long SAMPLE_INTERVAL_MS = 5000UL;
constexpr uint16_t SERIAL_BAUD_RATE = 9600;
constexpr uint8_t FLOW_DECIMAL_PLACES = 2;
constexpr uint8_t TEMPERATURE_DECIMAL_PLACES = 2;
constexpr uint8_t ROOM_DECIMAL_PLACES = 1;
constexpr uint8_t PRESSURE_DECIMAL_PLACES = 2;

// Flow configuration retained from the current pump-room firmware.
constexpr LabPulse::PulseFlowConfig FLOW1_CONFIG = {
    3, 450.0F, INPUT_PULLUP, FALLING};
constexpr LabPulse::PulseFlowConfig FLOW2_CONFIG = {
    2, 450.0F, INPUT_PULLUP, FALLING};

// Water-temperature configuration retained from the current firmware.
constexpr LabPulse::ThermistorConfig TEMPERATURE_CONFIGS[] = {
    {A0, 5.0F, 1023, 2, 1021, 4700.0F, 0.0014948F, 0.00021902F,
     1.6239e-6F, 3.4445e-8F, -100.0F, 200.0F},
    {A1, 5.0F, 1023, 2, 1021, 4700.0F, 0.0014948F, 0.00021902F,
     1.6239e-6F, 3.4445e-8F, -100.0F, 200.0F},
    {A2, 5.0F, 1023, 2, 1021, 4700.0F, 0.0014948F, 0.00021902F,
     1.6239e-6F, 3.4445e-8F, -100.0F, 200.0F},
    {A3, 5.0F, 1023, 2, 1021, 4700.0F, 0.0014948F, 0.00021902F,
     1.6239e-6F, 3.4445e-8F, -100.0F, 200.0F},
};

// DHT11 configuration retained from the current pump-room firmware.
constexpr LabPulse::Dht11Config DHT11_CONFIG = {
    4, DHT11, -40.0F, 80.0F, 0.0F, 100.0F};

// The pump-room transducers use the legacy 5.0 / 1024.0 ADC scaling and clamp.
constexpr LabPulse::LinearPressureConfig PRESSURE1_CONFIG = {
    A5, 5.0F, 1024, 2, 1021, 0.5F, 4.5F, 1.6F, 10.0F, 0.0F,
    -0.25F, 16.5F, true};
constexpr LabPulse::LinearPressureConfig PRESSURE2_CONFIG = {
    A4, 5.0F, 1024, 2, 1021, 0.5F, 4.5F, 1.6F, 10.0F, 0.0F,
    -0.25F, 16.5F, true};

void setup();
void loop();

}  // namespace PumpRoomFirmware

#endif

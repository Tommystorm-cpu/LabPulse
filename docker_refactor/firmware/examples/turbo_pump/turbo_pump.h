#ifndef LABPULSE_TURBO_PUMP_FIRMWARE_H
#define LABPULSE_TURBO_PUMP_FIRMWARE_H

#include <Arduino.h>
#include <PinMeasurement.h>
#include <PulseFlowSensor.h>
#include <ThermistorSensor.h>

namespace TurboPumpFirmware {

constexpr unsigned long SAMPLE_INTERVAL_MS = 5000UL;
constexpr uint16_t SERIAL_BAUD_RATE = 9600;
constexpr uint8_t FLOW_DECIMAL_PLACES = 2;
constexpr uint8_t TEMPERATURE_DECIMAL_PLACES = 2;

// Authoritative pin-to-name mappings. Each record is {Arduino pin, serial
// measurement name}; both the sensor setup and serial output use these fields.
constexpr LabPulse::PinMeasurement FLOW1 = {2, "flow1"};
constexpr LabPulse::PinMeasurement FLOW2 = {3, "flow2"};
constexpr LabPulse::PinMeasurement TEMPERATURES[] = {
    {A0, "triton1#temp1"},
    {A1, "triton1#temp2"},
    {A2, "triton2#temp1"},
    {A3, "triton2#temp2"},
};

// Flow configuration retained from the current turbo-pump firmware.
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

void setup();
void loop();

}  // namespace TurboPumpFirmware

#endif

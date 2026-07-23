#ifndef LABPULSE_PRESSURE_MONITOR_FIRMWARE_H
#define LABPULSE_PRESSURE_MONITOR_FIRMWARE_H

#include <Arduino.h>
#include <LinearPressureSensor.h>
#include <PinMeasurement.h>

namespace PressureMonitorFirmware {

// Device configuration retained from the currently deployed pressure monitor.
constexpr unsigned long SAMPLE_INTERVAL_MS = 1000UL;
constexpr uint16_t SERIAL_BAUD_RATE = 9600;
constexpr uint8_t PRESSURE_DECIMAL_PLACES = 2;

// Authoritative pin-to-name mapping. Edit this one record to change either the
// Arduino input or the serial measurement name.
constexpr LabPulse::PinMeasurement PRESSURE = {A0, "pressure"};

constexpr LabPulse::LinearPressureConfig PRESSURE_CONFIG = {
    PRESSURE.pin,
    5.0F,    // ADC reference volts
    1023,    // ADC divisor
    2,       // minimum valid ADC
    1021,    // maximum valid ADC
    0.48F,   // minimum calibration voltage
    4.5F,    // maximum calibration voltage
    1.6F,    // full-scale pressure in MPa
    10.0F,   // convert MPa to bar
    10000.0F,  // preserve legacy four-decimal MPa quantisation
    -0.25F,  // minimum valid output in bar
    16.5F,   // maximum valid output in bar
    false,   // preserve legacy negative readings above the validity floor
};

void setup();
void loop();

}  // namespace PressureMonitorFirmware

#endif

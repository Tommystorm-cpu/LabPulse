#ifndef LABPULSE_PRESSURE_MONITOR_FIRMWARE_H
#define LABPULSE_PRESSURE_MONITOR_FIRMWARE_H

#include <Arduino.h>
#include <LinearPressureSensor.h>
#include <PinMeasurement.h>
#include <Sht40Sensor.h>

namespace PressureMonitorFirmware {

// These values match the deployed monitor so adopting the shared firmware
// library does not silently change its serial output or sampling rate.
constexpr unsigned long SAMPLE_INTERVAL_MS = 1000UL;
constexpr uint16_t SERIAL_BAUD_RATE = 9600;
constexpr uint8_t PRESSURE_DECIMAL_PLACES = 2;
constexpr uint8_t ENVIRONMENT_DECIMAL_PLACES = 2;

// Authoritative pin-to-name mapping. Edit this one record to change either the
// Arduino input or the serial measurement name.
constexpr LabPulse::PinMeasurement PRESSURE = {A0, "pressure"};

// The SHT40 uses the Arduino's fixed I2C SDA/SCL pins and produces two named
// measurements from its fixed 0x44 address.
struct Sht40Measurements {
  const char *temperatureName;
  const char *humidityName;
};
constexpr Sht40Measurements ENVIRONMENT = {"temperature", "humidity"};

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

constexpr LabPulse::Sht40Config SHT40_CONFIG = {
    -40.0F,  // minimum valid temperature in degrees C
    85.0F,   // maximum valid temperature in degrees C
    0.0F,    // minimum valid relative humidity percentage
    100.0F,  // maximum valid relative humidity percentage
};

void setup();
void loop();

}  // namespace PressureMonitorFirmware

#endif

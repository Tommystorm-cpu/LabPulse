\*
Header code to run the DHT11 on an arduino
*\

#ifndef TH_SENSOR_CODE_H
#define TH_SENSOR_CODE_H

// Check Arduino version
#if defined(ARDUINO) && (ARDUINO >= 100)
  #include <Arduino.h>
#else
  #include <WProgram.h>
#endif

// Library version
#define DHT11LIB_VERSION "0.4.1"

// Return status codes
#define DHTLIB_OK              0
#define DHTLIB_ERROR_CHECKSUM -1
#define DHTLIB_ERROR_TIMEOUT  -2

/**
 * Class to read temperature and humidity from a DHT11 sensor.
 * Usage:
 *    dht11 DHT;
 *    int result = DHT.read(pin);
 *    if (result == DHTLIB_OK) {
 *        int temp = DHT.temperature;
 *        int hum = DHT.humidity;
 *    }
 */
class dht11 {
public:
    /**
     * Reads temperature and humidity data from the DHT11 sensor.
     * 
     * @param pin The Arduino digital pin connected to the DHT11 data line.
     * @return One of the status codes: DHTLIB_OK, DHTLIB_ERROR_CHECKSUM, or DHTLIB_ERROR_TIMEOUT.
     */
    int read(int pin);

    // Public members to hold sensor readings
    int humidity;
    int temperature;
};

#endif  // TH_SENSOR_CODE_H

/*
Code to generate the temperature of a water temperature sensor from a resistor

This code should be either downloaded into the Arduino IDE as a .cpp
file or copy and pasted into one.
*/

//Checks that the ARDUINO is defined and is version 1.0.0 or greater
//If it is it uses the Arduino.h program, if not it uses a legacy program 
//called WProgam.h
#if defined(ARDUINO) && (ARDUINO >= 100)
#include <Arduino.h>
#else
#include <WProgram.h>
#endif

//Define class for the sensor
class WT_sensor {
  public:
    float read(int pin,
      float A,
      float B,
      float C,
      float D,
      float Res_const
      );
        float Temperature;
}

/*
Function from WT_sensor class called read.
*/
float WT_sensor::read(int pin,
                      float A,
                      float B,
                      float C,
                      float D,
                      float Res_const){
  //Read voltage across sensor, assuming the supply voltage is 5.0V and 10-bit ADC
  float voltage = analogRead(pin) * (5.0 / 1023.0);
  float res_cont_voltage = 5.0 - voltage;

  float Res_sensor = (voltage/res_const_voltage) * Res_const;
  float lnR = log (Res_sensor)
  Temperature = (A + B * (lnR) + C * (lnR ** 2) + D * (lnR ** 3)) ** -1;

  return Temperature
}

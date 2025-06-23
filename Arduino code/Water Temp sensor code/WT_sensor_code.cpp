/*
Code to generate the temperature of a water temperature sensor from a resistor

This code should be either downloaded into the Arduino IDE as a .cpp
file or copy and pasted into one.
*/
//include math.h module to use the natural log
#include <math.h>

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
    float Res_sensor;
};

/*
Function from WT_sensor class called read, its inputs are the pin number to use
from A0-A5, the Steinhart-Hart parameters A,B,C and D and the resistance of the 
constant resistor in the voltage divider circuit.

This function outputs the temperature output of the sensor, but also the resistance
of the sensor for testing.
*/
float WT_sensor::read(int pin,
                      float A,
                      float B,
                      float C,
                      float D,
                      float Res_const){
  //Read voltage across sensor, assuming the supply voltage is 5.0V and 10-bit ADC
  float voltage = analogRead(pin) * (5.0 / 1023.0);
  //Total supply is 5.0V, hence the constant resistor must have this voltage
  float res_const_voltage = 5.0 - voltage;

  //Calculate the sensors resistance
  Res_sensor = (voltage/res_const_voltage) * Res_const;
  float lnR = log (Res_sensor);

  //Steinhart-Hart equation - converted to celcius
  Temperature = (1.0 / (A + B * (lnR) + C * pow(lnR,2) + D * pow(lnR,3))) - 273.15;
  
  return Temperature;
}

/*
Header file to run the water temperature sensor on an Arduino
*/

#ifndef WT_sensor_code_H
#define WT_sensor_code_H

// Check Arduino version
#if defined(ARDUINO) && (ARDUINO >= 100)
  #include <Arduino.h>
#else
  #include <WProgram.h>
#endif

//Define class in .cpp file
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

#endif

#include "WT_sensor_code.h"
#include <list>

T_sens WT_sensor;

//Define all pins used - up to 6 analog pins available
list<int> pins = {A0};
int num_pins = pins.size()

float A = 0.0014948;
float B = 0.00021902;
float C = 1.6239e-6;
float D = 3.4445e-8;
float Res_const = 2000;

void setup() {
  Serial.begin(9600); // Start serial communication
}

int i = 0
void loop() {
  float Temperature = T_sens.read(pins[i],
  A,
  B,
  C,
  D,
  Res_const);

  Serial.print("Temperature across pin ");
  Serial.print(i);
  Serial.println(Temperature);

  i++;
  if (i == num_pins) {
    i = 0;
    delay(5000);
  }
}

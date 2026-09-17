//Define all pins used - up to 6 analog pins available
//Note that you must change the i value in the loop() to 
//match the number of entries in the list
int pins[2] = {A0,A1};

//Steinhart-Hart parameters determined by python curve_fitting
float A = 0.0014948;
float B = 0.00021902;
float C = 1.6239e-6;
float D = 3.4445e-8;
//Resistance of the constant resistor used
float Res_const = 2200;

void setup() {
  Serial.begin(9600); // Start serial communication
}

//Initialise on pin 0, and check each pin's output
int i = 0;
void loop() {
  //Read voltage across sensor, assuming the supply voltage is 5.0V and 10-bit ADC
  float voltage = analogRead(pins[i]) * (5.0 / 1023.0);
  //Total supply is 5.0V, hence the constant resistor must have this voltage
  float res_const_voltage = 5.0 - voltage;

  //Calculate the sensors resistance
  float Res_sensor = (voltage/res_const_voltage) * Res_const;
  float lnR = log (Res_sensor);

  //Steinhart-Hart equation - converted to celcius
  float Temperature = (1.0 / (A + B * (lnR) + C * pow(lnR,2) + D * pow(lnR,3))) - 273.15;
  
  //Print the temperature/resistance output 
  //Use resistance for testing circuit with known resistors.
  Serial.print("Temperature across pin ");
  Serial.print(i);
  Serial.print(" ");
  Serial.println(Temperature);
  /*Serial.print("Sensor Resistance of sensor ");
  Serial.print(i);
  Serial.print(" ");
  Serial.println(T_sens.Res_sensor);*/

  //Move to the next pin
  i++;
  //If every pin has been read, wait 5 seconds and start again
  if (i == 2) {
    i = 0;
    delay(5000);
  }
}

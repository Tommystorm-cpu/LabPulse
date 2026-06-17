/*
This code is here just in case it is desired to replace the flow sensors with pressure sensors to reduce impedance.

This code is written to gather temperature and flow rate data for pipes but has not been tested on the actual circuit.
*/

//List of analogue pins used for temp sensors
int T_pins[2] = {A0,A1};
//Steinhart-Hart parameters determined by python curve_fitting
float A = 0.0014948;
float B = 0.00021902;
float C = 1.6239e-6;
float D = 3.4445e-8;
//Resistance of the constant resistor used
float Res_const = 4700;

float readTemperature(float T_voltage) {
  /*
  Function to calculate the temperature reading of an NTC thermistor using the Steinhart-Hart equation.
  Its only input is voltage, however it is necessary to define the Steinhart-Hart equations parameters
  at the start of the script. If in future you are using multiple sensors with different parameters, 
  then change this function to take A,B,C,D as inputs.
  */
  
  //Total supply is 5.0V, hence the constant resistor must have this voltage
  float res_const_voltage = 5.0 - T_voltage;
  //Calculate the sensors resistance
  float Res_sensor = (voltage/res_const_voltage) * Res_const;
  float lnR = log(Res_sensor);

  //Steinhart-Hart equation - converted to celcius
  float Temperature = (1.0 / (A + B * (lnR) + C * pow(lnR,2) + D * pow(lnR,3))) - 273.15;]
  return Temperature
}
int P_pins[2] = {A2,A4};
//Start_V should be calibrated just at atmospheric pressure - nominally it's 0.5V but can be slightly different
float Start_V = 0.5;
float End_V = 4.5;
float linear_gradient = (End_V - Start_V) / 1.6;

float readPressure(float P_voltage) {
  float Pressure = (P_voltage - Start_V) / linear_gradient;
}

//Create variables for Hagen–Poiseuille equation
float flowRate;
float len_pipe;
float dyn_vis;
float area;

float measureViscosity(float T_voltage) {
  float water_temp = readTemperature(T_voltage);
}

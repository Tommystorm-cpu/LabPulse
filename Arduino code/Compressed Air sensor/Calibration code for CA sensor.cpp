/*
Code to copy and paste into a .ino file to calibrate the DFRobot SEN057 sensor.

To calibrate, simply turn on the sensor at ambient pressure and measure the output voltage.
The output voltage should be roughly 0.5V, but whatever result is obtained should be used in
place of the Start_V variable in the Arduino_instructions_for_CA_sensor code.
*/

//The analog pin number
int pin = 0;

void setup() {
  Serial.begin(9600);
}

void loop() {
  //Read voltage
  float output_V = analogRead(pin) * (5.0 / 1023.0);

  //Output voltage
  Serial.print(output_V);
  Serial.println(" V")
  
  delay(5000);
}

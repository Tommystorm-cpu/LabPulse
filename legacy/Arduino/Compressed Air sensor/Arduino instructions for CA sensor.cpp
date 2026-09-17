/*
Code to copy into the .ino file and upload to an arduino to read the DFRobot SEN057.
*/

//Define initial variables
//Analog pin number
int pin = 0;
//Start_V should be calibrated just at atmospheric pressure - nominally it's 0.5V but can be slightly different
float Start_V = 0.5;
float End_V = 4.5;

float linear_gradient = (End_V - Start_V) / 1.6;

char userInput = '\0';  // To store Y/N input
void setup() {
 Serial.begin(9600); 
 Serial.println("Do you want Absolute pressure? (Y/N)");

 // Wait for a valid input
 while (true) {
   if (Serial.available()) {
     char c = Serial.read();

     // Wait for newline (user pressed Enter)
     if (c == 'Y' || c == 'y') {
       userInput = 'Y';
       break;
     } else {
       userInput = 'N';
       break;
   }
  }
 }
}

void loop() {
  //Read voltage across sensor, assuming the supply voltage is 5.0V and 10-bit ADC
  float V_output = analogRead(pin) * (5.0 / 1023.0);

  float Pressure = (V_output - Start_V) / linear_gradient;
  
  if (userInput == 'Y') {
    Pressure += 0.101325;
  }
  
  Serial.print("Pressure: ");
  Serial.print(Rel_Pressure);
  Serial.println(" MPa");

  delay(5000);
}

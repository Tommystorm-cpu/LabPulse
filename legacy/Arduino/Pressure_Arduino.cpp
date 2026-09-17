// Initialise variables
int pin = 0; //Analogue pin number used
float Start_V = 0.48; //Calibrated start voltage at atmospheric pressure
float End_V = 4.5; //Equipment manual stated max output voltage
//generate gradient for linear fit
float linear_gradient = (End_V - Start_V) / 1.6;

void setup() {
  Serial.begin(9600);
}

void loop() {
  //Read voltage output
  float V_output = analogRead(pin) * (5.0 / 1023.0);
  //Convert to pressure with linear fit
  float Pressure = (V_output - Start_V) / linear_gradient;
  
  Serial.println(Pressure, 4);  // Send pressure value with 4 decimals
  delay(1000);
}
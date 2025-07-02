int pin = 0;
float Start_V = 0.5;
float End_V = 4.5;
float linear_gradient = (End_V - Start_V) / 1.6;

char userInput = 'Y';  // Hardcoded to 'Y' (absolute pressure)

void setup() {
  Serial.begin(9600);
  // No waiting for user input anymore
}

void loop() {
  float V_output = analogRead(pin) * (5.0 / 1023.0);
  float Pressure = (V_output - Start_V) / linear_gradient;

  if (userInput == 'Y') {
    Pressure += 0.101325;
  }

  Serial.println(Pressure, 4);  // Send pressure value with 4 decimals
  delay(1000);
}

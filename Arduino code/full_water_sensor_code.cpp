#include <Arduino.h>

int pins[4] = {A0,A1,A2,A3};

//Steinhart-Hart parameters determined by python curve_fitting
float A = 0.0014948;
float B = 0.00021902;
float C = 1.6239e-6;
float D = 3.4445e-8;
//Resistance of the constant resistor used
float Res_const = 4700;

byte sensorPin_1 = 2;
const byte sensorInterrupt_1 = digitalPinToInterrupt(sensorPin_1);
byte sensorPin_2 = 3;
const byte sensorInterrupt_2 = digitalPinToInterrupt(sensorPin_2);

// The hall-effect flow sensor outputs approximately 4.5 pulses per second per
// litre/minute of flow.
float calibrationFactor = 4.5;

volatile byte pulseCount_1;
volatile byte pulseCount_2;

float flowRate_1;
unsigned long flowMilliLitres;
unsigned long totalMilliLitres;

float flowRate_2;
unsigned long flowMilliLitres_2;
unsigned long totalMilliLitres_2;

unsigned long oldTime;

float readTemperature(int voltage) {
  //Total supply is 5.0V, hence the constant resistor must have this voltage
  float res_const_voltage = 5.0 - voltage;
  //Calculate the sensors resistance
  float Res_sensor = (voltage/res_const_voltage) * Res_const;
  float lnR = log(Res_sensor);

  //Steinhart-Hart equation - converted to celcius
  float Temperature = (1.0 / (A + B * (lnR) + C * pow(lnR,2) + D * pow(lnR,3))) - 273.15;]
  return Temperature
}

//Each turn of the water flow sensors wheel interrupts the program
//and adds on 1 to the pulseCount
void pulseCounter_1() {
  pulseCount_1++;
}

void pulseCounter_2() {
  pulseCount_2++;
}

void printResults() {
  detachInterrupt(sensorInterrupt_1);
  detachInterrupt(sensorInterrupt_2);
  
  flowRate_1 = ((1000.0 / (millis() - oldTime)) * pulseCount_1) / calibrationFactor;
  flowRate_2 = ((1000.0 / (millis() - oldTime)) * pulseCount_2) / calibrationFactor;
  
  totalLitres_1 += flowRate_1 / 60;
  totalLitres_2 += flowRate_2 / 60;
      
  Serial.print("Flow1: ");
  Serial.print(flowRate_1, 2);
  Serial.print(" L/min, Total1: ");
  Serial.print(totalLitres_1, 2);
  Serial.print(" L | ");
  
  Serial.print("Flow2: ");
  Serial.print(flowRate_2, 2);
  Serial.print(" L/min, Total2: ");
  Serial.println(totalLitres_2, 2);
      
  // --- Temperature Readings ---
  for (int i = 0; i < 4; i++) {
    float voltage = analogRead(pins[i]);
    float Temperature = readTemperature(voltage);
    Serial.print("Temperature across pin ");
    Serial.print(i);
    Serial.print("is ");
    Serial.print(Temperature);
    Serial.println("Celcius")
    }
}

void setup() {
  
  // Initialize a serial connection for reporting values to the host
  Serial.begin(9600);

  //Set input pin to accept signal
  pinMode(sensorPin, INPUT);
  digitalWrite(sensorPin, HIGH);

  //Initialise variables
  pulseCount        = 0;
  flowRate          = 0.0;
  flowMilliLitres   = 0;
  totalMilliLitres  = 0;
  oldTime           = 0;

  // The Hall-effect sensor is connected to pin 2 which uses interrupt 0.
  // Configured to trigger on a FALLING state change (transition from HIGH
  // state to LOW state)
  attachInterrupt(sensorInterrupt_1, pulseCounter_1, FALLING);
  attachInterrupt(sensorInterrupt_2, pulseCounter_2, FALLING);
}

void loop() {
  /* The Hall-effect sensor provides pulses corresponding to 4.5 per second per
  litre/min of flow. Since pulse count is stored as a byte, we can only store 255 
  pulses, so we must only count for every second.
  */
  int timecounter = 0;
  if (millis() - oldTime >= 1000) {
    timecounter++;

    if (timecounter == 3) {
      printResults();
      timecoutner = 0;
    }
     // Reset counters
    pulseCount_1 = 0;
    pulseCount_2 = 0;
    oldTime = millis();
    // Enable the interrupt again now that we've finished sending output
    attachInterrupt(sensorInterrupt_1, pulseCounter_1, FALLING);
    attachInterrupt(sensorInterrupt_2, pulseCounter_2, FALLING);
  }
}


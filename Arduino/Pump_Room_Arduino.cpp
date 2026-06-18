#include <Arduino.h>
#include <DHT.h>

// --- NEW HARDWARE PINS ---
#define DHTPIN 4          // Digital pin 4 for DHT11
#define DHTTYPE DHT11     // DHT 11 model
#define PRESS_PIN_1 A5    // Analog pin for Pressure Sensor 1 (Triton 1)
#define PRESS_PIN_2 A4    // Analog pin for Pressure Sensor 2 (Triton 2)

// Initialize DHT sensor
DHT dht(DHTPIN, DHTTYPE);

// Pressure Sensor Max Range (1.6 MPa = 16 bar)
float P_MAX = 1.6; 

// --- EXISTING CONFIGURATION ---
int a_pins[4] = {A0,A1,A2,A3};

float A = 0.0014948;
float B = 0.00021902;
float C = 1.6239e-6;
float D = 3.4445e-8;

float Res_const = 4700;

// Corrected Flow Sensor Pins
byte sensorPin_1 = 3;     // Triton 1
const byte sensorInterrupt_1 = digitalPinToInterrupt(sensorPin_1);
byte sensorPin_2 = 2;     // Triton 2
const byte sensorInterrupt_2 = digitalPinToInterrupt(sensorPin_2);

float calibrationFactor = 450.0; 
float flowCount_1 = 0.0;
float flowCount_2 = 0.0;
float flowRate_1 = 0.0;
float flowRate_2 = 0.0;
unsigned long oldTime = 0.0;

// --- FUNCTIONS ---
float readTemperature(float voltage) {
  float res_const_voltage = 5.0 - voltage;
  float Res_sensor = (voltage/res_const_voltage) * Res_const;
  float lnR = log(Res_sensor);
  float Temperature = (1.0 / (A + B * (lnR) + C * pow(lnR,2) + D * pow(lnR,3))) - 273.15;
  return Temperature;
}

void flowCounter_1() {
  flowCount_1 += 1.0 / calibrationFactor;
}

void flowCounter_2() {
  flowCount_2 += 1.0 / calibrationFactor;
}

void printResults() {
  detachInterrupt(sensorInterrupt_1);
  detachInterrupt(sensorInterrupt_2);

  // 1. Calculate Flow
  float duration = ((millis() - oldTime)/1000.0)/60.0;
  flowRate_1 = flowCount_1 / duration;
  flowRate_2 = flowCount_2 / duration;

  // 2. Read New Sensors (DHT11 & Pressure)
  float roomTemp = dht.readTemperature();
  float roomHum = dht.readHumidity();

  // Convert raw analog (0-1023) to voltage (0-5V)
  float voltageP1 = analogRead(PRESS_PIN_1) * (5.0 / 1024.0);
  float voltageP2 = analogRead(PRESS_PIN_2) * (5.0 / 1024.0);

  // Apply DFRobot Pressure Formula AND convert to bar (* 10.0)
  float press1_bar = (((voltageP1 - 0.5) / 4.0) * P_MAX) * 10.0;
  float press2_bar = (((voltageP2 - 0.5) / 4.0) * P_MAX) * 10.0;

  // Filter out negative noise if pressure is below zero
  if (press1_bar < 0) press1_bar = 0.0;
  if (press2_bar < 0) press2_bar = 0.0;

  // 3. Print Output
  // Print Flow
  Serial.print("Flow1: "); Serial.print(flowRate_1, 2); Serial.print(" L/min | ");
  Serial.print("Flow2: "); Serial.print(flowRate_2, 2); Serial.println(" L/min");

  // Print Water Temps
  int len = sizeof(a_pins) / sizeof(a_pins[0]);
  for (int i = 0; i < len; i++) {
    float voltage = analogRead(a_pins[i]) * (5.0/1023.0);
    float Temperature = readTemperature(voltage);
    Serial.print("Temp"); Serial.print(i); Serial.print(": ");
    Serial.print(Temperature, 2); Serial.print("C  ");
  }
  Serial.println("");

  // Print NEW Sensors
  Serial.print("RoomTemp: "); Serial.print(roomTemp, 1); Serial.print("C | ");
  Serial.print("RoomHum: "); Serial.print(roomHum, 1); Serial.print("% | ");
  Serial.print("Press1: "); Serial.print(press1_bar, 2); Serial.print(" bar | ");
  Serial.print("Press2: "); Serial.print(press2_bar, 2); Serial.println(" bar");
}

void setup() {
  Serial.begin(9600);
  dht.begin();

  pinMode(sensorPin_1, INPUT);
  digitalWrite(sensorPin_1, HIGH);
  pinMode(sensorPin_2, INPUT);
  digitalWrite(sensorPin_2, HIGH);

  attachInterrupt(sensorInterrupt_1, flowCounter_1, FALLING);
  attachInterrupt(sensorInterrupt_2, flowCounter_2, FALLING);
}

void loop() {
  if (millis() - oldTime >= 5000.0) {
    printResults();
    flowCount_1 = 0.0;
    flowCount_2 = 0.0;
    oldTime = millis();
    attachInterrupt(sensorInterrupt_1, flowCounter_1, FALLING);
    attachInterrupt(sensorInterrupt_2, flowCounter_2, FALLING);
  }
}
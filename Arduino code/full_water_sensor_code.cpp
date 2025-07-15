#include <Arduino.h>

// --- Temperature Sensor Setup ---
const int analogPins[4] = {A0, A1, A2, A3};
const float seriesResistor = 10000; // 10k?
const float nominalResistance = 10000; // Thermistor resistance at 25ï¿½C
const float nominalTemperature = 25;
const float bCoefficient = 3950;
const int adcMax = 1023;

float readTemperature(int adcValue) {
  float voltage = adcValue / (float)adcMax;
  float resistance = seriesResistor * (1.0 / voltage - 1.0);

  float steinhart;
  steinhart = resistance / nominalResistance;
  steinhart = log(steinhart);
  steinhart /= bCoefficient;
  steinhart += 1.0 / (nominalTemperature + 273.15);
  steinhart = 1.0 / steinhart;
  steinhart -= 273.15;

  return steinhart;
}

// --- Flow Sensor Setup ---
volatile int flowCount1 = 0;
volatile int flowCount2 = 0;
unsigned long lastTime = 0;
float calibrationFactor = 4.5; // Pulses per second per L/min
float totalLitres1 = 0;
float totalLitres2 = 0;

void flow1ISR() {
  flowCount1++;
}

void flow2ISR() {
  flowCount2++;
}

void setup() {
  Serial.begin(9600);

  // Flow sensor interrupts
  attachInterrupt(digitalPinToInterrupt(2), flow1ISR, RISING);
  attachInterrupt(digitalPinToInterrupt(3), flow2ISR, RISING);

  lastTime = millis();
}

void loop() {
  unsigned long currentTime = millis();

  if (currentTime - lastTime >= 2000) {  // Every 2 seconds
    // --- Temperature Readings ---
    for (int i = 0; i < 4; i++) {
      int adcValue = analogRead(analogPins[i]);
      float tempC = readTemperature(adcValue);
      Serial.print("Temp");
      Serial.print(i);
      Serial.print(": ");
      Serial.print(tempC, 2);
      Serial.print(" ï¿½C  ");
    }
    Serial.println();

    // --- Flow Rate Readings ---
    float flowRate1 = (flowCount1 / calibrationFactor); // L/min
    float flowRate2 = (flowCount2 / calibrationFactor);

    totalLitres1 += flowRate1 / 60.0 * 2.0; // 2 seconds interval
    totalLitres2 += flowRate2 / 60.0 * 2.0;

    Serial.print("Flow1: ");
    Serial.print(flowRate1, 2);
    Serial.print(" L/min, Total1: ");
    Serial.print(totalLitres1, 2);
    Serial.print(" L | ");

    Serial.print("Flow2: ");
    Serial.print(flowRate2, 2);
    Serial.print(" L/min, Total2: ");
    Serial.println(totalLitres2, 2);
    
    // Reset counters
    flowCount1 = 0;
    flowCount2 = 0;
    lastTime = currentTime;
  }
}


volatile int pulseCount = 0;
float flowRate = 0.0;
float totalLitres = 0.0;
unsigned long lastMeasurement = 0;

const byte flowPin = 2;
const float calibrationFactor = 4.5; // Usually 7.5 pulses per second per L/min

void pulseCounter() {
  pulseCount++;
}

void setup() {
  Serial.begin(9600);
  pinMode(flowPin, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(flowPin), pulseCounter, RISING);
  lastMeasurement = millis();
}

void loop() {
  unsigned long currentTime = millis();

  if (currentTime - lastMeasurement >= 5000) {
    detachInterrupt(digitalPinToInterrupt(flowPin));

    float elapsed = (currentTime - lastMeasurement) / 1000.0;
    flowRate = (pulseCount / calibrationFactor) / elapsed; // L/min
    float litresThisInterval = (pulseCount / calibrationFactor) / 60.0 * elapsed;
    totalLitres += litresThisInterval;

    Serial.print("FlowRate:");
    Serial.print(flowRate, 3);
    Serial.print(",TotalLitres:");
    Serial.println(totalLitres, 3);

    pulseCount = 0;
    lastMeasurement = currentTime;

    attachInterrupt(digitalPinToInterrupt(flowPin), pulseCounter, RISING);
  }
}

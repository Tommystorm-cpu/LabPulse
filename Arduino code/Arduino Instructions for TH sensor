#include "TH_sensor_code.cpp"

TH_sensor_code DHT;

void setup() {
  Serial.begin(9600);
}

void loop() {
  int chk = DHT.read(2);  // Reads sensor on pin D2
  Serial.print("Temperature: ");
  Serial.print(DHT.temperature);
  Serial.print(" °C, Humidity: ");
  Serial.print(DHT.humidity);
  Serial.println(" %");
  delay(2000);
}

#include "TH_sensor_code.h"

dht11 DHT;
int pin_num = 2; // Replace 2 with the correct pin

void setup() {
  Serial.begin(9600); // Start serial communication
}

void loop() {
  int result = DHT.read(pin_num);

  if (result == DHTLIB_OK) {
    Serial.print("Temp: ");
    Serial.print(DHT.temperature);
    Serial.print("°C  Hum: ");
    Serial.print(DHT.humidity);
    Serial.println("%");
  } 
  if (result == DHTLIB_ERROR_TIMEOUT) {
    Serial.print("Timeout Error");
  }
  if (result == DHTLIB_ERROR_CHECKSUM) {
    Serial.print("CHECKSUM error");
  }
  delay(2000);
}

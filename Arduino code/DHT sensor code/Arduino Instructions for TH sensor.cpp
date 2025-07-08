//Include the dht11 class and define an object of that class
#include "TH_sensor_code.h"
dht11 DHT;

//Digital pin number
int pin_num = 2; 

void setup() {
  Serial.begin(9600); 
}

void loop() {
  //Use DHT.read function, it returns temperature and humidity
  int result = DHT.read(pin_num);

  //If no errors return print results
  if (result == DHTLIB_OK) {
    Serial.print("Temp: ");
    Serial.print(DHT.temperature);
    Serial.print("°C  Hum: ");
    Serial.print(DHT.humidity);
    Serial.println("%");
  } else if (result == DHTLIB_ERROR_TIMEOUT) {
    Serial.print("Timeout Error");
  } else if (result == DHTLIB_ERROR_CHECKSUM) {
    Serial.print("CHECKSUM error");
  } else {
    Serial.print("Something has gone wrong")
  }
  //Wait 2 seconds before next reading
  delay(2000);
}

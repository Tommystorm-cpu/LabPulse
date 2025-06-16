/*
Code for the Arduino to copy and paste into the IDE. 

This code runs the TH_sensor_code.cpp file assuming it has been imported
as a git file
*/

#include "pathname.h"

pathname DHT;

//Pin number, assuming it is pin D2, but should be changed if otherwise
int pin = 2;
//Sets up the baud rate to be 9600
void setup() {
    Serial.begin(9600);
}

void loop() {
    int check = DHT.read(pin);
    
    if (check == 0) {
        Serial.print("Temperature: ");
        Serial.print(DHT.temperature);
        Serial.print(" °C, Humidity: ");
        Serial.print(DHT.humidity);
        Serial.println(" %");
        delay(2000);
    }
    if (check == -1) {
        Serial.print("Checksum Error");
        delay(2000);
    }
    if (check == -2) {
        Serial.print("Timeout Error");
        delay(2000);
    }

}

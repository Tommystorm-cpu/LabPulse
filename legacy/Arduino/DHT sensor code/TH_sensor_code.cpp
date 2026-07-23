/*
Code for an Arduino to import into an IDE, then communicate with a DHT11 
sensor. This code should be either downloaded into the Arduino IDE as a .cpp
file or copy and pasted into one.
*/

//Checks that the ARDUINO is defined and is version 1.0.0 or greater
//If it is it uses the Arduino.h program, if not it uses a legacy program 
//called WProgam.h
#if defined(ARDUINO) && (ARDUINO >= 100)
#include <Arduino.h>
#else
#include <WProgram.h>
#endif

//Defines the DHT11 library version. The current is 0.4.1
#define DHT11LIB_VERSION "0.4.1"

/*
Defines error check variables, DHTLIB_OK is returned if the function 
succeeds in measurement, DHTLIB_ERROR_CHECKSUM is returned if the 
function has an unknown error - likely occuring from an error in 
transmission of data between the sensor and arduino, finally the 
DHTLIB_ERROR_TIMEOUT is returned if at any point the system runs for too
long without a succesful change. 
*/
#define DHTLIB_OK	0
#define DHTLIB_ERROR_CHECKSUM	-1
#define DHTLIB_ERROR_TIMEOUT	-2

//Class dht11 that defines the read function and the humidity and temp.
class dht11
{
public:
    int read(int pin);
	int humidity;
	int temperature;
};

/*
The function read from the dht11 class. 
Note that this function doesn't return temperature and humidity,
instead it defines them as values determined in the function, which can
then be accessed by later code
*/
// Return values:
// DHTLIB_OK
// DHTLIB_ERROR_CHECKSUM
// DHTLIB_ERROR_TIMEOUT
//Function provides a value to temperature and humidity but doesn't explicitly return them
int dht11::read(int pin)
{
	/*
    Defines the bits list as a list of 5 entries, which is then 
    expanded to 5 entries of 8 bits each (5 bytes).
    Defines count as 7, this variable will be used to sweep for each 
    bit of a byte.
    Defines idx as the number of each byte, which will increase by 1 
    each loop. 
    
    Each value in the bits list, and in cnt and idx is an unsigned 8bit
    integer. 

    Altogether this creates a system that gathers 5 bytes of binary 
    data, with temperature and humidity value between 0,255. 
    This limit isn't a concern however, since the DHT11 sensor 
    ranges between 0-50 celcius and 20-90% humidity.
    */
	uint8_t bits[5];
	uint8_t cnt = 7;
	uint8_t idx = 0;

    // Initialises each byte to be of value 0
	for (int i=0; i< 5; i++) bits[i] = 0;

	// Sends a signal to the sensor that requests an output
	pinMode(pin, OUTPUT); //Sets pin to provide power to sensor
	digitalWrite(pin, LOW); //Sets pin to 0V
	delay(18); //Waits 18ms
	digitalWrite(pin, HIGH); //Powers pin to 3.3V or 5V
	delayMicroseconds(40); //Allows this power to transfer for 40Microseconds
	pinMode(pin, INPUT); //Sets pin to input and HIGH
    /*Pin is now in state to accept message, and if a voltage pulse is 
    received then it outputs HIGH (1) or LOW (0) if no signal is received
    */

	// Tests if the sensor is sending an alternating signal. 
    // If not then a timeout error will be returned.
	unsigned int loopCnt = 10000;
	while(digitalRead(pin) == LOW)
		if (loopCnt-- == 0) return DHTLIB_ERROR_TIMEOUT;

	loopCnt = 10000;
	while(digitalRead(pin) == HIGH)
		if (loopCnt-- == 0) return DHTLIB_ERROR_TIMEOUT;

	// READ OUTPUT - 40 BITS => 5 BYTES or TIMEOUT
	for (int i=0; i<40; i++)
	{
        // Repeats timeout test
		loopCnt = 10000;
		while(digitalRead(pin) == LOW)
			if (loopCnt-- == 0) return DHTLIB_ERROR_TIMEOUT;

        //Time taken to start high pulse
		unsigned long t = micros();

		loopCnt = 10000;
		while(digitalRead(pin) == HIGH)
			if (loopCnt-- == 0) return DHTLIB_ERROR_TIMEOUT;
        /*
        micros() here is the time taken to end the high pulse. Hence this
        checks if the duration of the pulse is greater than 40 
        microseconds. If it is, it makes the cnt bit of the idx byte in
        the bits list 1.
        */
		if ((micros() - t) > 40) bits[idx] |= (1 << cnt);
		if (cnt == 0)   //The bits of the idx byte is completed
		{
			cnt = 7;    // restart at MSB
			idx++;      // next byte!
		}
		else cnt--;
	}

		humidity    = bits[0]; 
		temperature = bits[2]; 
    //Check for potential transmission errors
	uint8_t sum = bits[0] + bits[1] + bits[2] + bits[3]; 
	//Serial.print(sum);
	//Serial.print(bits[4]);
	if (bits[4] != sum & 0xFF) {
    return DHTLIB_ERROR_CHECKSUM;
  }
	return DHTLIB_OK;
}

//
// END OF FILE
//

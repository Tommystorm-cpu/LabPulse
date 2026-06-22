=============================================================================
                      THE LABPULSE DECLARATIVE FLOW
=============================================================================

 1. THE BLUEPRINT
 ----------------
 [ config.yaml ]  <-- You type: "I have a DHT sensor on GPIO Pin 4"
        |
        v

 2. THE MASTER HUB (The only script actually "running")
 ----------------
 [ main.py ]      <-- Reads YAML, wakes up, and calls the Factory.
        |
        v

 3. THE MATCHMAKER
 ----------------
 [ sensor_factory.py ] <-- Looks at YAML, matches sensors to Drivers.
        |
        +-----------------------+-----------------------+-----------------+
        |                       |                       |                 |
        v                       v                       v                 v

 4. THE DRIVERS 
 ----------------
 [ serial_driver.py ]   [ gpio_driver.py ]   [ i2c_driver.py ]   [ modbus_driver.py ]
        |                       |                       |                 |
        v                       v                       v                 v

 5. THE HARDWARE
 ----------------
 [ Arduino/Pumps ]        [ DHT11 Sensor ]    [ Pressure Board ]  [ Turbo Pump ]
        |                       |                       |                 |
        +-----------------------+-----------------------+-----------------+
                                |
                                v
                           (Raw Data)

 6. THE UNIFICATION
 ----------------
 [ main.py ]  <-- The Hub collects raw data from all 4 drivers, standardizes 
        |         it into a single, clean format, and evaluates thresholds.
        v

 7. THE OUTPUT
 ----------------
 [ MQTT Broker ]  <-- A single, synchronized stream of data is 
        |             published to the broker.
        v
 [ Home Assistant ]
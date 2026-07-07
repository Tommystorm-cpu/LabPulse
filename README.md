# LabPulse

LabPulse is a small-scale monitoring system for lab infrastructure. We built it for our research group to monitor the building services on which [our experiments](https://wp.lancs.ac.uk/laird-group/) rely - power, chilled water, compressed air, etc. We can monitor their status online, and if any of them is interrupted the users receive a text alert. We think of it as a small-scale building management system.

LabPulse runs on a Raspberry Pi and uses the [Home Assistant](https://www.home-assistant.io/) web interface. The Pi is connected to various sensors controlled by Arduinos.

This Github contains a shopping list, code, and CAD files for our system, which was built by two interns at Lancaster University in the course of one summer. LabPulse is still very much a prototype, but it has already helped us respond quickly to what would otherwise have been an experimental interruption. We welcome attempts to replicate and improve it, and are happy to answer questions as time allows.

<center>
<img src="./Documentation/LabPulse%20cartoon-03.png" alt="What LabPulse does" width="800"/>
</center>

## Contents of this repository

This repository consists of the code, instructions, 3D printable schematics and some introductory PCB designs for a lab monitoring set up.

This set up aims to automate some aspects of lab management, mainly that of monitoring some different systems and sending alerts to lab workers when emergency thresholds are breached. For example, using a Gravity Analog Water Pressure Sensor, we successfully, remotely, monitor the compressed air pressure. Or likewise, using several GE-1337 temperature sensors and Gravity water flow meters we also monitor the water temperature and flow rate in the cooling pipes of the ULT lab.

There is still massive potential to extend this repository to include other sensors and monitoring systems, and likely the existing code could be improved to be more efficient or accurate. For example, we have not yet produced a framework for monitoring oxygen or CO2 levels (although our lab and most labs with liquid nitrogen already have O2 sensors for safety reasons), useful data to monitor could also be air quality; especially with regards to labs where chemistry or semiconductor manufacture takes place.

The current set up in the ULT lab is depicted in the Set_up_flowchart.pdf and described below.
[Diagram flowchart](Set_up_flowchart.pdf)

The Raspberry Pi:
Our Pi, set up with a UPS hat and SIM hat, is the powerhouse of the set up. It powers and receives sensor data from the Arduino Uno's, is powered via barrel jack and connected to two batteries through the UPS hat. If a power outage occurs, or say the coolant water temperature raises beyond threshold, the Pi uses the SIM hat to send a text to anyone on the phone number list in Raspberry Pi code/Config files and scripts/phone_number_config.json - note these phone numbers are not real for obvious reasons. Additionally, outside of errors, the Pi uploads to Home Assistant, allowing for remote check-ins.

Arduino's:
Each arduino is powered by the Pi through a USB hub, and prints the values to Serial, which the Pi monitors in their own virtual environment. There are PCBs in the PCB_files file, in which can be used with 4 temperature sensors and 2 water flow sensors as a hat, allowing for relatively clean wiring. These PCBs definitely can be improved, but should work and will be worked on in future. 

Set up of Arduino's is rather simple, upload the code to the arduino through the Pi or via a personal computer with USB, connect the required sensors to the corresponding pins and then connect to the Pi. Note that one common issue we have ran into is when disconnecting and reconnecting an Arduino, sometimes the USB ports change, e.g. from dev/tty/ACM0 to dev/tty/ACM1. In the Pi's code, change the USB port in the corresponding script from the Python publishing scripts file to the correct one. To check the correct one you can type ls /dev/ttyACM*, and this will list all connected ports of this type.

Below is a summary of each file and its contents and uses.

3D printable parts:
In this file are any 3D models we used to place the raspberry pi with the UPS and SIM hats on.

Arduino:
Here is all the code used to publish onto the arduino's using the Arduino IDE through the raspberry Pi. The one caveat here is for two of our arduino's we used full_water_sensor_code.cpp to monitor our sensors, which include 4 temperature sensors and 2 water flow sensors. If you wish to monitor only temperature, then you would have to use code from the corresponding file.

General error detection code:
These files of code are to monitor the data output of the sensors and create an alert if and when there are issues. The only one currently used as of the 22nd December 2025 is the Upper_lower_limits.py, however, you can adapt the other code to monitor for any spikes in data such as the mean temperature or flow rate, and you can use the code to raise an error if one sensor reports differently to the others.

PCB_files:
These files contain the prototypes used for an arduino hat. The first works but is messy and uses male and female header pins - therefore isn't great. There are prototypes of an arduino hat, showing the progress made. If you were to use this PCB design for 4 temperature sensors and 2 water flow sensors, use the final prototype file for your gerber file, or use it as inspiration to design your own.

archive_v1_pi_code:
Contains an archive of the pi code before the alterations were made in accordance with the project review found in the documentation folder.

Installation: 
Contains the installation guide, compatability checks and installation script to install the LabPulse infrastructure through a USB thumb-drive.
For the newer Docker Compose based prototype, see [docker_refactor/CONTAINER_SETUP.md](docker_refactor/CONTAINER_SETUP.md).

pi_scripts:
This directory contains the core Python architecture for LabPulse. These scripts run continuously as background`systemd services to process hardware data, evaluate it against thresholds, and trigger alerts. 
* config.yaml: The master configuration file. All hardware limits, calibration offsets, and SMS contact numbers are set here.
* pumproompub.py, pressurepub.py, etc.: The main service scripts that read the Arduino serial inputs, validate them, and route them to Home Assistant via MQTT.
* labpulse_common/: The shared library folder containing the sms.py 4G cellular engine and the mqtt_health.py heartbeat tracker.

For general enquiries, feel free to open an issue.

# 🔬 LabPulse: Universal Sensor Hub

Welcome to the LabPulse repository if you are reading this, you are likely taking over the maintenance and expansion of the LabPulse IoT environment. 

This folder contains the **Sensor Abstraction Plug-in Architecture**, an expansive rewrite of the original LabPulse system. 

---

## 🏗️ The Architecture Shift
**The Old System ():** Imperative design. We ran 5 separate Python background services simultaneously. Each script was hardcoded to look for specific USB ports, parse specific text strings, and handle its own MQTT connection. Adding a new sensor required writing a completely new background service from scratch.

**The New System:** Declarative design. We run one single Master Hub (`main.py`). The Hub is completely blind to hardware. It simply reads a `config.yaml` file, dynamically loads the passive "Drivers" requested in the config, asks them for data every 2 seconds, and beams the results to Home Assistant.

### The 5 Core Components
1. **The Contract (`sensor_base.py`)**: An Abstract Base Class that forces all future hardware drivers to look identical (`.setup()`, `.read()`, `.disconnect()`).
2. **The Blueprint (`config.yaml`)**: A single inventory list of every connected piece of hardware.
3. **The Bouncer (`config.py`)**: A Pydantic engine that strictly validates the YAML file on boot to prevent typos from crashing the system.
4. **The Matchmaker (`sensor_factory.py`)**: Dynamically links the YAML blueprint to the physical Python driver scripts.
5. **The Drivers (`drivers/serial_driver.py`)**: Passive translator scripts that just read hardware (like Arduino USB ports) and return a Python dictionary.

---

## 📂 Directory Structure
Ensure your files are placed in this exact structure on the Raspberry Pi (`~/lab_pulse/`):

```text
lab_pulse/
├── main.py                          # The Master Hub Execution Loop
├── config.yaml                      # The only file you ever manually edit
├── thresholds.json                  # Dynamically updated by Home Assistant
├── labpulse_common/
│   ├── __init__.py
│   ├── config.py                    # Pydantic Schemas
│   ├── sensor_base.py               # The Abstract Base Contract
│   ├── sensor_factory.py            # Dynamic Module Loader
│   ├── mqtt_health.py               # Watchdog / Health Tracker
│   ├── sms.py                       # Cellular SMS Engine
│   └── drivers/
│       ├── __init__.py
│       └── serial_driver.py         # Universal pipe-delimited Arduino parser
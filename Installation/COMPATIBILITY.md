# Explicit Compatibility Matrix

LabPulse v2.0 is rigorously tested against the following software and hardware environments. 

| Component | Minimum Supported Version | Recommended / Target | Notes |
| :--- | :--- | :--- | :--- |
| **Operating System** | Debian 11 (Bullseye) | Raspberry Pi OS (Bookworm 64-bit) | Must have `systemd` support for daemons. |
| **Python Version** | Python 3.9 | Python 3.11+ | Python 3.11 provides significant speedups for background loops. |
| **Host Hardware** | Raspberry Pi 3B+ | Raspberry Pi 4 Model B (4GB) | Pi 5 requires `lgpio` for GPIO mapping. |
| **MQTT Broker** | Mosquitto v1.6+ | Eclipse Mosquitto v2.0+ | Hosted locally on `localhost:1883`. |
| **Arduino Nodes** | Arduino Uno R3 | Arduino Mega 2560 | Must connect via `/dev/serial/by-id/` stable symlinks. |
| **I2C Power Sensor** | INA219 (Generic) | Adafruit INA219 | Address default `0x42`. I2C must be enabled in Pi BIOS. |
| **Cellular Modem** | ModemManager Compliant | Quectel EC25 / Sixfab 4G HAT | Requires active SIM without PIN lock. |
| **Pydantic** | `v2.0` | `v2.4+` | LabPulse `config.py` relies on strictly typed v2 schemas. |
| **Paho-MQTT** | `v2.0.0` | `v2.1.0` | Version 2.x introduces breaking API changes; do not downgrade to 1.6.x. |
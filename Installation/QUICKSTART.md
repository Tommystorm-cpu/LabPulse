# 🚀 LabPulse v2.0 - 30 Minute Quick Start Guide

Follow these exact steps to deploy LabPulse onto a factory-reset Raspberry Pi.

### Step 1: Flash the OS (Day Zero Prep)
1. Open the **Raspberry Pi Imager** on your PC.
2. Select **Raspberry Pi OS (64-bit)**.
3. Click the **Gear Icon** (Advanced Customization).
4. **CRITICAL:** Check "Set username and password" and set the username strictly to **`monitorpi`**.
5. Check "Configure wireless LAN" and enter the lab's Wi-Fi network.
6. Check "Enable SSH".
7. Click **Write**.

### Step 2: Hardware Assembly
1. Power off the Pi. Insert the micro-SD card.
2. Plug the Arduinos (Pump Room, Pressure, Turbo Pump) into the USB ports.
3. Wire the INA219 UPS chip to the I2C pins.
4. Power on the Pi.

### Step 3: One-Click Execution
1. Copy this entire repository to your `Vaunix` USB drive.
2. Plug the USB drive into the Raspberry Pi.
3. SSH into the Pi (or open a terminal) and run:
   ```bash
   sudo /media/monitorpi/Vaunix/lab_pulse/installation/bootstrap_pi.sh
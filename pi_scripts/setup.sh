#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# --- UI COLORS ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   LabPulse Telemetry Setup Wizard     ${NC}"
echo -e "${BLUE}=======================================${NC}\n"

# --- 1. PRIVILEGE CHECK ---
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Please run this installer as root (use sudo).${NC}"
  exit 1
fi

# Determine the absolute path of the project root (one directory up from the script)
PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
echo -e "${GREEN}[OK]${NC} Project root identified at: $PROJECT_ROOT"

# --- 2. HARDWARE VALIDATION ---
echo -e "\n${YELLOW}---> Validating Hardware Prerequisites...${NC}"

# Check for I2C (For the UPS and Pressure sensors)
if ls /dev/i2c-* 1> /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} I2C interface is enabled."
else
    echo -e "${RED}[ERROR] I2C is not enabled. Please run 'sudo raspi-config', enable I2C under Interfacing Options, and reboot.${NC}"
    exit 1
fi

# Check for Cellular Modem (ModemManager)
if command -v mmcli >/dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} ModemManager is installed."
else
    echo -e "${YELLOW}[WARN] ModemManager not found. SMS alerts will fail.${NC}"
    read -p "Do you want to install ModemManager now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        apt-get update && apt-get install -y modemmanager
    fi
fi

# Check for Arduinos (USB Serial connection)
# List the devices, filter for the word "Arduino", and count the lines (-l)
ARDUINO_COUNT=$(ls /dev/serial/by-id/ 2>/dev/null | grep -i "Arduino" | wc -l || true)

if [ "$ARDUINO_COUNT" -gt 0 ]; then
    echo -e "${GREEN}[OK]${NC} Detected $ARDUINO_COUNT Arduino(s) via USB."
else
    echo -e "${YELLOW}[WARN] No Arduino found on USB. Pump & Temp data will not feed until plugged in.${NC}"
fi

# --- 3. PYTHON & DEPENDENCIES ---
echo -e "\n${YELLOW}---> Setting up Python Environment...${NC}"

# Ensure pip and venv are installed
apt-get update -yqq
apt-get install -yqq python3-pip python3-venv i2c-tools

# Create a unified master Virtual Environment for the whole lab
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo -e "Creating unified virtual environment in $PROJECT_ROOT/venv..."
    python3 -m venv "$PROJECT_ROOT/venv"
else
    echo -e "${GREEN}[OK]${NC} Virtual environment already exists."
fi

# Install requirements (Assuming you create a requirements.txt later)
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    echo "Installing Python dependencies..."
    $PROJECT_ROOT/venv/bin/pip install -r "$PROJECT_ROOT/requirements.txt"
else
    echo -e "${YELLOW}[WARN] No requirements.txt found. Installing default packages...${NC}"
    $PROJECT_ROOT/venv/bin/pip install pyserial paho-mqtt smbus2
fi

# --- 4. CONFIGURATION TEMPLATES ---
echo -e "\n${YELLOW}---> Provisioning Configuration Files...${NC}"

# Safely copy templates without overwriting existing live configs
for template in "$PROJECT_ROOT/templates/"*.template.json; do
    if [ -f "$template" ]; then
        config_file="$PROJECT_ROOT/$(basename "$template" .template.json).json"
        if [ ! -f "$config_file" ]; then
            cp "$template" "$config_file"
            echo -e "${GREEN}[OK]${NC} Provisioned $config_file from template."
        else
            echo -e "${GREEN}[OK]${NC} $config_file already exists. Skipping..."
        fi
    fi
done

# --- 5. SYSTEMD SERVICE REGISTRATION ---
echo -e "\n${YELLOW}---> Registering Background Services...${NC}"

SERVICE_DIR="$PROJECT_ROOT/systemd"

if [ -d "$SERVICE_DIR" ]; then
    for service_file in "$SERVICE_DIR/"*.service; do
        if [ -f "$service_file" ]; then
            service_name=$(basename "$service_file")
            echo "Installing $service_name..."
            
            # Copy the service file to the systemd directory
            cp "$service_file" /etc/systemd/system/
            
            # Update permissions
            chmod 644 "/etc/systemd/system/$service_name"
        fi
    done

    echo "Reloading systemd daemon..."
    systemctl daemon-reload

    echo "Enabling services to start on boot..."
    for service_file in "$SERVICE_DIR/"*.service; do
        if [ -f "$service_file" ]; then
            service_name=$(basename "$service_file")
            systemctl enable "$service_name"
            systemctl restart "$service_name"
            echo -e "${GREEN}[OK]${NC} $service_name is active and enabled."
        fi
    done
else
    echo -e "${RED}[ERROR] No systemd directory found at $SERVICE_DIR${NC}"
fi

echo -e "\n${BLUE}=======================================${NC}"
echo -e "${GREEN}   Setup Complete! System is LIVE.     ${NC}"
echo -e "${BLUE}=======================================${NC}"

#!/bin/bash
# LabPulse v2.0 - Ultimate One-Click Setup Wizard

# Exit immediately if a command exits with a non-zero status
set -e

# --- UI COLORS ---
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}=================================================${NC}"
echo -e "${BLUE}       LabPulse Telemetry - Setup Wizard         ${NC}"
echo -e "${BLUE}=================================================${NC}\n"

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Please run this installer as root (use sudo).${NC}"
  exit 1
fi

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
VENV_DIR="$PROJECT_ROOT/waterenv"
echo -e "${GREEN}[OK]${NC} Project root locked at: $PROJECT_ROOT"

# --- LINUX DEPENDENCIES ---
echo -e "\n${YELLOW}---> Fetching Core OS Dependencies...${NC}"
apt-get update -yqq
apt-get install -yqq python3-pip python3-venv i2c-tools rsync modemmanager
echo -e "${GREEN}[OK]${NC} Linux packages & ModemManager installed."

# --- HARDWARE VALIDATION & AUTO-FIX ---
echo -e "\n${YELLOW}---> Validating Hardware Prerequisites...${NC}"
if ls /dev/i2c-* 1> /dev/null 2>&1; then
    echo -e "${GREEN}[OK]${NC} I2C interface is already enabled."
else
    echo -e "${YELLOW}[WARN] I2C is disabled. Auto-enabling now...${NC}"
    raspi-config nonint do_i2c 0
    echo -e "${GREEN}[OK]${NC} I2C interface enabled via hardware toggle."
fi

ARDUINO_COUNT=$(ls /dev/serial/by-id/ 2>/dev/null | grep -i "Arduino" | wc -l || true)
if [ "$ARDUINO_COUNT" -gt 0 ]; then
    echo -e "${GREEN}[OK]${NC} Detected $ARDUINO_COUNT Arduino(s) via USB."
else
    echo -e "${YELLOW}[WARN] No Arduino found on USB. Systems will wait for hardware.${NC}"
fi

# --- PYTHON ENVIRONMENT ---
echo -e "\n${YELLOW}---> Setting up Python Environment...${NC}"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" -q
    echo -e "${GREEN}[OK]${NC} Python dependencies locked."
else
    echo -e "${RED}[ERROR] requirements.txt not found!${NC}"
    exit 1
fi

# --- CONFIGURATION TEMPLATES ---
echo -e "\n${YELLOW}---> Provisioning Configuration Files...${NC}"
if [ -d "$PROJECT_ROOT/templates" ]; then
    for template in "$PROJECT_ROOT/templates/"*.template.*; do
        if [ -f "$template" ]; then
            config_file="$PROJECT_ROOT/$(basename "$template" | sed 's/\.template//')"
            if [ ! -f "$config_file" ]; then
                cp "$template" "$config_file"
                echo -e "${GREEN}[OK]${NC} Provisioned $config_file"
            else
                echo -e "${GREEN}[OK]${NC} $config_file already live. Skipping overwrite."
            fi
        fi
    done
fi

# --- SYSTEMD SERVICE REGISTRATION ---
echo -e "\n${YELLOW}---> Registering Background Services...${NC}"
SERVICES=("pumproompub" "pressurepub" "turbo_pump_monitor" "powerpub" "dhtpub")

for SERVICE in "${SERVICES[@]}"; do
    if [ -f "$PROJECT_ROOT/${SERVICE}.py" ]; then
        SERVICE_FILE="/etc/systemd/system/labpulse_${SERVICE}.service"
        cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=LabPulse Monitor - ${SERVICE}
After=network.target

[Service]
Type=simple
User=monitorpi
WorkingDirectory=$PROJECT_ROOT
ExecStart=$VENV_DIR/bin/python $PROJECT_ROOT/${SERVICE}.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
        chmod 644 "$SERVICE_FILE"
        systemctl enable "labpulse_${SERVICE}.service" >/dev/null 2>&1
        systemctl restart "labpulse_${SERVICE}.service"
        echo -e "${GREEN}[OK]${NC} ${SERVICE} activated."
    fi
done

systemctl daemon-reload
echo -e "\n${BLUE}=================================================${NC}"
echo -e "${GREEN}   Setup Complete! LabPulse System is LIVE.      ${NC}"
echo -e "${BLUE}=================================================${NC}"
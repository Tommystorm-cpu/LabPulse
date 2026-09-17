#!/bin/bash

# Exit immediately on error
set -e

# Variables
PYTHON_VERSION="3.13.2"
HA_DIR="/srv/homeassistant_313"
HA_USER="monitorpi"  # <-- Change to your username!

echo "=== Updating system and installing dependencies ==="
sudo apt update
sudo apt upgrade -y
sudo apt install -y build-essential libssl-dev zlib1g-dev \
  libncurses5-dev libncursesw5-dev libreadline-dev libsqlite3-dev \
  libgdbm-dev libdb5.3-dev libbz2-dev libexpat1-dev liblzma-dev \
  libffi-dev uuid-dev wget autoconf

echo "=== Downloading and building Python $PYTHON_VERSION ==="
cd /usr/src
sudo wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz
sudo tar xzf Python-$PYTHON_VERSION.tgz
cd Python-$PYTHON_VERSION
sudo ./configure --enable-optimizations
sudo make -j$(nproc)
sudo make altinstall

echo "=== Creating Home Assistant virtual environment ==="
sudo mkdir -p $HA_DIR
sudo chown $HA_USER:$HA_USER $HA_DIR
cd $HA_DIR

/usr/local/bin/python3.13 -m venv .
source bin/activate

echo "=== Installing Home Assistant ==="
python3.13 -m pip install --upgrade pip
pip install wheel
pip install homeassistant

echo "=== Creating systemd service ==="
SERVICE_FILE="/etc/systemd/system/home-assistant@$HA_USER.service"
sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Home Assistant
After=network.target

[Service]
Type=simple
User=$HA_USER
ExecStart=$HA_DIR/bin/hass -c $HA_DIR/.homeassistant
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

echo "=== Enabling and starting Home Assistant service ==="
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable home-assistant@$HA_USER
sudo systemctl start home-assistant@$HA_USER

echo "✅ Setup complete!"
echo "Access Home Assistant at: http://$(hostname -I | awk '{print $1}'):8123"

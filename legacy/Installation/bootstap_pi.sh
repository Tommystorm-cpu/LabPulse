#!/bin/bash
# LabPulse v2.0 - One-Click USB Bootstrap Installer

# Update DEST_DIR if your USB name changes from Vaunix
USB_DIR="/media/monitorpi/Vaunix/lab_pulse"
PI_DIR="/home/monitorpi/lab_pulse"

echo "========================================"
echo " Starting LabPulse USB Deployment..."
echo "========================================"

# 1. Copy the codebase to the Pi's internal storage
echo "📦 Copying files from Vaunix to internal SD card..."
cp -r "$USB_DIR" /home/monitorpi/

# 2. Fix Linux execution permissions
echo "🔧 Setting secure execution permissions..."
chmod -R 755 "$PI_DIR"
chmod +x "$PI_DIR/setup.sh"
chmod +x "$PI_DIR/sync_usb.sh"

# 3. Handoff to the main setup wizard
echo "🚀 Executing main LabPulse Setup Wizard..."
cd "$PI_DIR" || exit
sudo ./setup.sh

echo "========================================"
echo "✅ Bootstrap Complete! LabPulse safely moved to internal storage."
echo "========================================"
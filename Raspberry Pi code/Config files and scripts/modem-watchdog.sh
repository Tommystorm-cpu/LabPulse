#!/bin/bash

LOG="/var/log/modem-watchdog.log"
echo "$(date): Running modem watchdog" >> "$LOG"

MODEM=$(mmcli -L 2>/dev/null | grep -o '/org/freedesktop/ModemManager1/Modem/[0-9]*')

if [ -z "$MODEM" ]; then
    echo "$(date): [ERROR] No modem found. Restarting ModemManager..." >> "$LOG"
    systemctl restart ModemManager
    sleep 10
    MODEM=$(mmcli -L 2>/dev/null | grep -o '/org/freedesktop/ModemManager1/Modem/[0-9]*')
fi

if [ -n "$MODEM" ]; then
    STATE=$(mmcli -m "$MODEM" | grep 'connected' | sed 's/\x1B\[[0-9;]\{1,\}[A-Za-z]//g' | awk '{print $NF}')
    if [ "$STATE" != "connected" ]; then
        echo "$(date): [WARN] Modem not connected. Attempting to reconnect..." >> "$LOG"
        mmcli -m "$MODEM" --simple-connect="apn=your.apn.here" >> "$LOG" 2>&1 #Make sure to change your.apn.here to the apn of your SIM service provider!
    else
        echo "$(date): [OK] Modem connected." >> "$LOG"
    fi
else
    echo "$(date): [FAIL] Still no modem after restart. Consider reboot." >> "$LOG"
    # reboot  # Uncomment only if you want to reboot after failure
fi

exit 0  # <<< Add this to prevent systemd from marking the service as failed

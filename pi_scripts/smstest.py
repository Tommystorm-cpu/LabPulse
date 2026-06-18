#!/usr/bin/env python

import subprocess
import sys
print (sys.executable)
import logging
from labpulse_common.config import load_recipients

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] - %(message)s')
logger = logging.getLogger("InteractiveSMSTest")

MESSAGE = "Test message from Laird lab monitor. Can be ignored."

def get_modem_index():
    try:
        result = subprocess.run(["mmcli", "-L"], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if "/Modem/" in line:
                return line.strip().split('/')[-1].split()[0]
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to list modems: {e.stderr}")
    return None

def send_sms(number, message):
    try:
        MODEM_INDEX = get_modem_index()
        if not MODEM_INDEX:
            return False
            
        create_cmd = ["mmcli", "-m", str(MODEM_INDEX), f"--messaging-create-sms=number='{number}',text='{message}'"]
        output = subprocess.run(create_cmd, capture_output=True, text=True, check=True).stdout

        sms_path = None
        for line in output.splitlines():
            if "SMS" in line and "/" in line:
                sms_path = line.strip().split()[-1]
                break
        
        if not sms_path:
            return False

        subprocess.run(["mmcli", "-s", sms_path, "--send"], check=True)
        logger.info(f"SUCCESS: Pushed to {number}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Hardware Error: {e.stderr}")
        return False

def main():
    recipients = load_recipients()
    if not recipients:
        logger.error("No contacts found in config.yaml.")
        sys.exit(1)

    print("\n--- LabPulse Phonebook ---")
    for idx, number in enumerate(recipients, start=1):
        print(f"[{idx}] {number}")
    print("[0] Cancel\n")

    while True:
        try:
            choice = input("Select user: ").strip()
            if choice == '0': sys.exit(0)
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(recipients):
                selected = recipients[choice_idx]
                break
        except ValueError:
            print("Invalid input.")

    success = send_sms(selected, MESSAGE)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

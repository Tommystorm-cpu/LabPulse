import queue
import subprocess
import threading
import time
import traceback

class LabPulseSMS:
    def __init__(self, recipients):
        self.recipients = recipients
        self.sms_queue = queue.Queue()
        # Automatically spin up an isolated background worker thread
        threading.Thread(target=self._sms_sender_worker, daemon=True).start()

    def _get_modem_index(self):
        try:
            # Add sudo to ensure the background service has permission to query the modem
            result = subprocess.run(["sudo", "mmcli", "-L"], capture_output=True, text=True, check=True)
            for line in result.stdout.splitlines():
                if "/Modem/" in line:
                    parts = line.strip().split("/")
                    return parts[-1].split()[0]
        except subprocess.CalledProcessError as e:
            print(f"[SMS ERROR] Failed to list modems: {e.stderr}")
        return None

    def send_sms(self, phone_number: str, message: str, retries=3):
        """Attempts to dispatch an SMS with retry buffers to handle modem collisions."""
        for attempt in range(retries):
            try:
                modem_index = self._get_modem_index()
                if not modem_index:
                    print("[SMS ERROR] No operational cellular modem found.")
                    return False

                print(f"[SMS] Staging text to {phone_number} (Attempt {attempt + 1}/{retries})")
                
                # Wrap the message in single quotes so the modem's internal parser accepts spaces and newlines
                sms_args = f"text='{message}',number={phone_number}"
                
                result = subprocess.run(
                    ["sudo", "mmcli", "-m", modem_index, "--messaging-create-sms", sms_args],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                # If the modem rejects the command, print the reason why
                if result.returncode != 0:
                    print(f"[SMS ERROR] Modem rejected SMS creation: {result.stderr.strip()}")
                    time.sleep(2)
                    continue

                sms_path = None
                for line in result.stdout.splitlines():
                    if "Successfully created new SMS" in line:
                        sms_path = line.split()[-1].strip()
                        break

                if not sms_path:
                    print(f"[SMS ERROR] Failed to parse SMS storage path from: {result.stdout}")
                    return False

                print(f"[SMS] Dispatched request via path: {sms_path}")
                
                # Add sudo to authorize the actual send command
                subprocess.run(["sudo", "mmcli", "-s", sms_path, "--send"], check=True, capture_output=True, text=True)
                print(f"[SMS SUCCESS] Alert delivered to {phone_number}!")
                return True

            except subprocess.TimeoutExpired as e:
                print(f"[SMS WARN] Modem timed out. Retrying... Context: {e}")
                time.sleep(2)
            except subprocess.CalledProcessError as e:
                print(f"[SMS WARN] Modem collision or failure. Retrying... Context:\n{e.stderr.strip() if e.stderr else e}")
                time.sleep(2)
            except Exception:
                print("[FATAL SMS ERROR] Unexpected framework error in dispatch:")
                traceback.print_exc()
                time.sleep(2)
        return False

    def _sms_sender_worker(self):
        while True:
            phone_number, message = self.sms_queue.get()
            try:
                self.send_sms(phone_number, message)
            except Exception:
                print("[FATAL SMS ERROR] Background pipeline failure:")
                traceback.print_exc()
            finally:
                self.sms_queue.task_done()

    def broadcast(self, message: str):
        """Pushes alerts into the background worker queue for all active contacts."""
        for number in self.recipients:
            self.sms_queue.put((number, message))

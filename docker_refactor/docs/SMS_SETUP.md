# LabPulse SMS Setup

LabPulse sends SMS alerts from the `labpulse-sms` container. Home Assistant does
not talk to the modem directly. Instead, generated alarm automations publish an
MQTT message to:

```text
labpulse/sms/send
```

The SMS container subscribes to `labpulse/sms/#`, formats the request, and sends
or logs it depending on `sms.backend` in the live config:

```yaml
sms:
  backend: "log"   # "log" for test systems, "mmcli" for the real modem Pi
  recipients:
    - "+447700900000"
```

The live config is:

```text
~/labpulse-ha/config.yaml
```

The repo template at `docker_refactor/config.yaml` is only copied as a starter.

## Backend Modes

`log` is the safe default. The SMS container receives MQTT alarm payloads and
writes what it would send to the container logs. It does not require a modem and
does not send real texts.

`mmcli` sends real SMS messages using ModemManager on the Raspberry Pi host.
Use this only on the Pi with the SIM/modem hardware installed.

## Real Pi Setup

Use this on the real Raspberry Pi that has the cellular modem.

1. Install and start ModemManager on the Pi host:

   ```bash
   sudo apt update
   sudo apt install -y modemmanager
   sudo systemctl enable --now ModemManager
   ```

2. Confirm the Pi can see the modem:

   ```bash
   mmcli -L
   ```

   You should see a path like:

   ```text
   /org/freedesktop/ModemManager1/Modem/0
   ```

3. Edit the live LabPulse config:

   ```bash
   nano ~/labpulse-ha/config.yaml
   ```

   Set:

   ```yaml
   sms:
     backend: "mmcli"
     recipients:
       - "+447700900000"
   ```

4. Regenerate Compose so the SMS container gets modem access:

   ```bash
   cd ~/labpulse-ha
   ./generate_compose.sh
   ```

   When `backend: "mmcli"` is set, the generated `labpulse-sms` service mounts:

   ```text
   /run/dbus
   /dev
   ```

   and runs privileged so `mmcli` inside the container can talk to the host
   ModemManager service.

5. Rebuild and restart:

   ```bash
   docker compose up -d --build
   ```

6. Check the SMS container can see the modem:

   ```bash
   docker compose exec labpulse-sms mmcli -L
   ```

7. Send a manual MQTT test:

   ```bash
   docker compose exec mosquitto mosquitto_pub \
     -h mosquitto \
     -t labpulse/sms/send \
     -m '{"title":"LabPulse SMS test","message":"Manual test from LabPulse","service":"manual","reading":"sms"}'
   ```

8. Watch the SMS logs:

   ```bash
   docker compose logs -f labpulse-sms
   ```

If the text does not arrive, first check `mmcli -L` on both the host and inside
the container. If the host sees the modem but the container does not, regenerate
Compose after confirming `sms.backend` is exactly `"mmcli"`.

## Test Pi Setup

Use this on the test Raspberry Pi with no modem.

1. Keep the SMS backend in log mode:

   ```yaml
   sms:
     backend: "log"
     recipients:
       - "+447700900000"
   ```

2. Regenerate and restart:

   ```bash
   cd ~/labpulse-ha
   ./generate_compose.sh
   docker compose up -d --build
   ```

3. Publish the same manual MQTT test:

   ```bash
   docker compose exec mosquitto mosquitto_pub \
     -h mosquitto \
     -t labpulse/sms/send \
     -m '{"title":"LabPulse SMS test","message":"Manual test from test Pi","service":"manual","reading":"sms"}'
   ```

4. Confirm the message was received and logged:

   ```bash
   docker compose logs labpulse-sms
   ```

   You should see a log line saying the log backend would send the SMS. No real
   SMS is sent in this mode.

## Home Assistant Alarm Test

Once Home Assistant is running, trip any LabPulse alarm boolean or set a
threshold so an alert automation fires. The generated automation publishes the
service and reading identity in the MQTT payload, so the SMS log/message should
include which sensor hub and reading tripped the alarm.

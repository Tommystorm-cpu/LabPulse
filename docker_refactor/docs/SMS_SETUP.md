# SMS Setup

LabPulse sends SMS alerts through the `labpulse-sms` container.

Home Assistant does not talk to the modem directly. Generated Home Assistant
alert automations publish MQTT messages to:

```text
labpulse/sms/send
```

The SMS container subscribes to:

```text
labpulse/sms/#
```

Then it formats and sends or logs the message depending on:

```yaml
sms:
  backend: "log"
```

in:

```text
~/labpulse-ha/config.yaml
```

## Backends

`log`:

- safe default
- no modem required
- writes the would-send message to logs
- best for development and test Pis

`mmcli`:

- sends real SMS messages
- requires ModemManager on the Pi host
- requires a visible modem/SIM
- causes Compose generation to give `labpulse-sms` modem access

## Config

```yaml
sms:
  backend: "log"
  recipients:
    - "+447700900000"
```

Change recipient numbers only in the live Pi config:

```text
~/labpulse-ha/config.yaml
```

After changing `sms.backend`, regenerate Compose:

```bash
cd ~/labpulse-ha
./generate_compose.sh
docker compose up -d --build
```

## MQTT Payload Shape

Generated alert automations publish JSON like:

```json
{
  "event": "alert",
  "service": "pressure_monitor",
  "service_label": "Air Pressure Sensor Hub",
  "reading": "pressure",
  "reading_label": "Pressure",
  "entity_id": "binary_sensor.labpulse_pressure_monitor_pressure_alarm",
  "title": "LabPulse Pressure alert",
  "message": "Air Pressure Sensor Hub / Pressure alarm is active.",
  "current": "0.8",
  "minimum_threshold": "1.0",
  "maximum_threshold": "999"
}
```

`sms_subscriber.py` accepts JSON payloads and falls back to plain text if the
payload is not JSON.

## Test Pi Setup

Use log mode:

```yaml
sms:
  backend: "log"
  recipients:
    - "+447700900000"
```

Regenerate and restart:

```bash
cd ~/labpulse-ha
./generate_compose.sh
docker compose up -d --build
```

Publish a manual test:

```bash
docker compose exec mosquitto mosquitto_pub \
  -h mosquitto \
  -t labpulse/sms/send \
  -m '{"title":"LabPulse SMS test","message":"Manual test from test Pi","service":"manual","reading":"sms"}'
```

Watch logs:

```bash
docker compose logs -f labpulse-sms
```

You should see that the log backend would send the SMS. No real SMS is sent.

## Real Modem Pi Setup

Use this only on the Raspberry Pi with the modem installed.

Install ModemManager on the host:

```bash
sudo apt update
sudo apt install -y modemmanager
sudo systemctl enable --now ModemManager
```

Confirm the host sees the modem:

```bash
mmcli -L
```

Expected output contains a modem path such as:

```text
/org/freedesktop/ModemManager1/Modem/0
```

Edit live config:

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

Regenerate and restart:

```bash
cd ~/labpulse-ha
./generate_compose.sh
docker compose up -d --build
```

When `backend: "mmcli"` is set, generated Compose gives `labpulse-sms`:

```text
/run/dbus:/run/dbus:ro
/dev:/dev
privileged: true
```

Check that the container sees the modem:

```bash
docker compose exec labpulse-sms mmcli -L
```

Publish a manual test:

```bash
docker compose exec mosquitto mosquitto_pub \
  -h mosquitto \
  -t labpulse/sms/send \
  -m '{"title":"LabPulse SMS test","message":"Manual test from LabPulse","service":"manual","reading":"sms"}'
```

Watch:

```bash
docker compose logs -f labpulse-sms
```

## Code Ownership

`labpulse_sms/sms_entry.py`:

- parses CLI args
- loads config
- creates sender
- creates subscriber
- loops forever

`labpulse_sms/sms_subscriber.py`:

- connects to MQTT
- subscribes to `labpulse/sms/#`
- parses payloads
- asks sender to broadcast messages

`labpulse_sms/sender.py`:

- formats SMS text
- queues outbound sends
- implements `log` backend
- implements `mmcli` backend

Home Assistant owns when alerts/recoveries happen. The SMS container only
delivers requests it receives.

## Troubleshooting

If no SMS log appears:

1. Check `labpulse-sms` is running.
2. Check Mosquitto is running.
3. Publish a manual MQTT test.
4. Watch `docker compose logs -f labpulse-sms`.
5. Confirm Home Assistant automation publishes to `labpulse/sms/send`.

If real SMS does not send:

1. Confirm `sms.backend: "mmcli"` in live config.
2. Run `./generate_compose.sh` after changing backend.
3. Confirm `mmcli -L` works on the host.
4. Confirm `docker compose exec labpulse-sms mmcli -L` works in the container.
5. Check SIM, signal, and modem status with ModemManager tools.

If the host sees the modem but the container does not, Compose was likely not
regenerated after switching to `mmcli`, or the container was not recreated.

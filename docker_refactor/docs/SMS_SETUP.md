# SMS Setup

LabPulse sends SMS alerts through the `labpulse-sms` container. Home Assistant
decides when an alarm transition warrants a message and publishes a validated
request to:

```text
labpulse/sms/send
```

The SMS worker subscribes to that exact topic at QoS 1, formats the request,
and either logs or sends it according to `sms.dry_run` in the live Pi config:

```text
~/labpulse-ha/config.yaml
```

## Configuration

Safe development configuration:

```yaml
sms:
  dry_run: true
  recipients:
    - "+447700900000"
```

Real modem configuration:

```yaml
sms:
  dry_run: false
  recipients:
    - "+447700900000"
```

Recipients must be unique international numbers beginning with `+` and
containing 8 to 15 digits. At least one recipient is required when `dry_run` is
`false`.
Keep real contact numbers only in the live Pi config; the repository
`docker_refactor/config.yaml` is a starter template.

After changing the delivery mode or recipients:

```bash
cd ~/labpulse-ha
./generate_compose.sh
docker compose up -d --build
```

## Delivery Modes

`dry_run: true` is the safe default. It needs no modem and logs the message with
recipient numbers masked.

`dry_run: false` sends through ModemManager using `mmcli`. Generated Compose gives only the SMS worker
the additional D-Bus, device, and privileged access required by the modem.
Created ModemManager SMS objects are removed after each attempt so modem storage
does not fill over time.

## Reliable Request Flow

Generated Home Assistant automations publish at QoS 1 with `retain: false`.
Every request has a stable unique `request_id`. The worker uses a persistent
MQTT session with client ID `LabPulse-SMS`, so Mosquitto can hold QoS 1 requests
while the worker is briefly offline.

Accepted request IDs are retained for 24 hours in:

```text
~/labpulse-ha/logs/sms_processed_requests.json
```

This prevents MQTT redelivery from sending the same SMS twice across worker
restarts. A 30-second per-service, reading, and event cooldown also protects
against accidental alert floods. The sender queue is bounded and drains during
normal container shutdown.

## MQTT Payload

Requests are strict JSON. Plain text, invalid UTF-8, missing fields, extra
fields, and unsupported events are rejected without sending an SMS.

```json
{
  "request_id": "labpulse_pressure_monitor_pressure_warning_20260713T140501123456",
  "event": "warning",
  "service": "pressure_monitor",
  "service_label": "Air Pressure Sensor Hub",
  "reading": "pressure",
  "reading_label": "Pressure",
  "state": "Danger",
  "title": "LabPulse Pressure warning",
  "message": "Air Pressure Sensor Hub / Pressure is in Danger.",
  "current": "0.8"
}
```

Required fields are `request_id`, `event`, `service`, `reading`, `state`,
`title`, and `message`. Labels and `current` are optional. Supported events are
`sensor_fault`, `warning`, `recovery`, and `test`.

## Status And Results

The worker publishes retained availability to:

```text
labpulse/sms/status
```

It also publishes Home Assistant MQTT discovery for
`sensor.labpulse_sms_status`. An unexpected disconnect uses the MQTT last will
to set the service offline.

Each recipient outcome is published at QoS 1 to:

```text
labpulse/sms/result/<request_id>
```

The result contains the request ID, masked recipient, `logged`, `sent`, or
`failed` status, optional detail, and a timestamp. Duplicate and rate-limited requests
also produce results explaining why they were rejected.

## Test In Dry-Run Mode

Create a unique ID and publish a complete test request:

```bash
docker compose exec mosquitto mosquitto_pub \
  -h mosquitto \
  -q 1 \
  -t labpulse/sms/send \
  -m '{"request_id":"manual-test-001","event":"test","service":"manual","reading":"sms","state":"Test","title":"LabPulse SMS test","message":"Manual test from LabPulse"}'
```

Use a new `request_id` for every manual test, then watch:

```bash
docker compose logs -f labpulse-sms
```

No real SMS is sent in log mode.

## Real Modem Setup

Install and start ModemManager on the Raspberry Pi host:

```bash
sudo apt update
sudo apt install -y modemmanager
sudo systemctl enable --now ModemManager
mmcli -L
```

Set `sms.dry_run: false`, regenerate Compose, recreate the stack, and confirm
the worker can see the modem:

```bash
docker compose exec labpulse-sms mmcli -L
```

The generated Mosquitto host port is bound to `127.0.0.1`, so it is available
to host-networked Home Assistant but not exposed directly to the lab LAN.
LabPulse containers continue to connect through the internal `mosquitto`
Compose service.

## Code Ownership

- `labpulse_sms/cli.py` loads config and owns graceful process shutdown.
- `labpulse_sms/subscriber.py` owns MQTT sessions, request validation,
  duplicate/flood protection, status, and results.
- `labpulse_sms/sender.py` owns formatting, the bounded queue, recipient fan-out,
  dry-run logging, ModemManager delivery, retries, and cleanup.
- `labpulse_common/mqtt_contracts.py` owns topics and the typed `SmsRequest`.
- `labpulse_common/config.py` owns delivery-mode and recipient validation.

Home Assistant remains the owner of alarm timing and transition decisions.

## Troubleshooting

If no request appears in SMS logs:

1. Check `docker compose ps` and `docker compose logs labpulse-sms`.
2. Confirm Mosquitto is running.
3. Confirm the payload includes a new valid `request_id` and all required fields.
4. Check `labpulse/sms/status` and the Home Assistant SMS status entity.
5. Inspect `labpulse/sms/result/<request_id>` for delivery outcomes.

If real delivery fails:

1. Confirm `sms.dry_run: false` and valid recipients in the live config.
2. Regenerate Compose after changing the delivery mode.
3. Run `mmcli -L` on the host.
4. Run `docker compose exec labpulse-sms mmcli -L` in the worker.
5. Check the SIM, signal, registration state, and ModemManager logs.

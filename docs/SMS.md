# SMS notifications

LabPulse has one SMS worker container. Home Assistant publishes validated
notification requests over MQTT; the worker routes them to dry-run logs, test
recipients, or normal recipients.

## Safe modes

### Dry run

Use during setup and development:

```yaml
sms:
  dry_run: true
  recipients:
    - "+447700900000"
  test_recipients:
    - "+447700900001"
```

The worker validates, deduplicates, and queues requests but logs masked
recipients instead of using a modem. Inbound `SUBSCRIBE` and `UNSUBSCRIBE`
commands are unavailable because the dry-run container deliberately has no
modem or D-Bus access.

### Home Assistant Test mode

Test mode is independent of `sms.dry_run`.

- Test mode on: requests are marked as tests, titles use `[TEST]`, and delivery
  targets only `test_recipients`.
- Test mode off: requests target only `recipients`.
- Global mute suppresses both modes.

Test mode starts on after every Home Assistant restart.

### Real modem delivery

Set `dry_run: false` only after the modem is verified and recipient lists have
been reviewed.

## Recipient configuration

Numbers must use international `+` format:

```yaml
sms:
  dry_run: false
  recipients:
    - "+441234567890"
  test_recipients:
    - "+449876543210"
```

Numbers contain 8 to 15 digits after `+`. Empty and duplicate entries are
rejected. At least one normal recipient is required for real delivery.

Do not commit real contact numbers.

## Modem setup

On the Raspberry Pi host:

```bash
sudo apt update
sudo apt install -y modemmanager
sudo systemctl enable --now ModemManager
mmcli -L
```

After setting `dry_run: false`, apply configuration and verify the modem inside
the container:

```bash
labpulse config
sudo docker compose -f ~/labpulse-live/compose.yaml \
  exec labpulse-sms mmcli -L
```

Real-mode Compose grants the SMS worker D-Bus and `/dev` access. Dry-run mode
does not.

## Send a manual test

Use a new request ID every time:

```bash
cd ~/labpulse-live
sudo docker compose exec mosquitto mosquitto_pub \
  -h mosquitto -q 1 -t labpulse/sms/send \
  -m '{"request_id":"manual-test-001","event":"test","service":"manual","measurement":"sms","state":"Test","title":"[TEST] LabPulse SMS test","message":"Manual test from LabPulse","test_mode":true}'
```

Watch:

```bash
labpulse logs -f labpulse-sms
```

Reusing an ID is intentionally rejected as a duplicate.

The Alarm Setup dashboard also provides a phone-book notification button. It
uses the active test/live recipient list and sends nothing while global mute is
on.

## Subscription commands

In real modem mode, a configured number may send:

```text
UNSUBSCRIBE
SUBSCRIBE
```

Matching is case-insensitive and ignores surrounding whitespace.

- `UNSUBSCRIBE` suppresses future normal and test alerts to that number.
- `SUBSCRIBE` restores both modes.
- The worker sends a confirmation.
- Unknown numbers and unknown commands receive no response.

Choices persist in:

```text
~/labpulse-live/logs/sms_subscriptions.json
```

The allow-list is built from both configured recipient lists. Restart
`labpulse-sms` after changing either list.

## Delivery safeguards

The SMS pipeline provides:

- strict request schema validation;
- QoS 1 MQTT subscription;
- persistent processed-request IDs;
- duplicate rejection;
- a 30-second per-event cooldown;
- a bounded queue;
- sequential sends;
- retries for modem failures;
- per-request result publication;
- online/offline worker status;
- graceful queue draining on shutdown.

Processed IDs are retained for 24 hours in:

```text
~/labpulse-live/logs/sms_processed_requests.json
```

## MQTT topics

```text
Request:  labpulse/sms/send
Status:   labpulse/sms/status
Result:   labpulse/sms/result/<request_id>
```

Requests contain a stable request ID, event kind, service, measurement, state,
title, message, and `test_mode`. Optional labels and the current measurement
provide human context.

## Operational acceptance

Before enabling live notifications:

1. Keep global mute on.
2. Verify the modem with `mmcli -L` on the host and in the container.
3. Enable Home Assistant Test mode.
4. Send a phone-book or manual test to one test recipient.
5. Verify `UNSUBSCRIBE` and `SUBSCRIBE`.
6. Confirm duplicate IDs do not resend.
7. Restart the SMS service and confirm subscription state persists.
8. Turn Test mode off only after reviewing normal recipients.
9. Deliberately unmute notifications.

## Troubleshooting

Check:

```bash
labpulse ps
labpulse logs -f labpulse-sms
sudo systemctl status ModemManager
mmcli -L
```

Common causes are dry-run mode, global mute, Test mode routing to a different
list, an unsubscribed number, invalid international formatting, missing
container modem access, or a duplicate/cooldown rejection.

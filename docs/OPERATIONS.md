# Operations

The installed configuration is `~/labpulse-live/config.yaml`. Edit that file,
then run `labpulse config` to validate and regenerate deployment files. The
repository `config.yaml` is only the starter copied during setup.

## Reading the system state

Treat the three displayed states independently:

- **Service health**: Online, Degraded, or Offline describes communication
  with a service, hub, or driver.
- **Reading availability**: Available, Unavailable, or Unavailable — optional
  describes one fresh numeric reading.
- **Alarm condition**: Normal or Danger evaluates thresholds only while the
  reading is available.

Current Problems contains confirmed incidents only. Diagnostics shows the raw
service state, availability policy, confirmation state, and delivery flags.
Clicking a measurement problem opens its alarm setup page.

## Notification controls

Global, setup, per-reading, and power mutes suppress delivery without changing
the underlying incident. Per-reading and power mutes also hide their condition
from Current Problems; Diagnostics remains available. Test mode selects the test recipient list. **Resend
active alert** retries the currently confirmed Danger or unavailable-reading
alert through the same central dispatcher and therefore respects maintenance
and every mute.

A recovery always dismisses the matching persistent Home Assistant problem.
LabPulse creates a recovery notification only when the corresponding opening
notification was created. SMS recovery additionally requires
`sms.send_recovery_sms: true`; it defaults to false.

## Safe updates

`labpulse update` requests retained maintenance before disrupting runtime
services. Home Assistant must acknowledge the same request ID. Update then
recreates the stack, waits for fresh telemetry from required readings only,
allows state reconciliation to settle, clears maintenance with another
acknowledgement, and starts SMS delivery. Threshold alarms then collect a new
observation window instead of reusing dangerous history from the restart.

If the command fails during that sequence, maintenance remains active and the
SMS worker remains stopped. Correct the reported service or required-reading
problem, verify telemetry, then run `labpulse up labpulse-sms`. Do not start the
worker separately without clearing acknowledged maintenance: a persistent MQTT
session may contain queued QoS 1 requests from an older deployment.

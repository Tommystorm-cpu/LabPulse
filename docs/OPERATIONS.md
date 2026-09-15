# Operations

The installed configuration is `~/labpulse-live/config.yaml`. Edit that file,
then run `labpulse config` to validate and regenerate deployment files. The
repository `config.yaml` is only the starter copied during setup.

## Reading the system state

System Status gives each service one operator-facing state:

- **Working**: the service and its required readings are current.
- **Needs attention**: the service is communicating but a component or required
  reading needs attention.
- **Offline**: LabPulse cannot communicate with the service.

Each card shows the latest values and explains a problem in plain language.
Measurements configured with `required: false` show **No recent data —
optional** when absent without changing the service from Working. Current
Problems contains confirmed, unmuted conditions and links to the relevant
alarm setup page.

## Notification controls

Global, setup, per-reading, and power mutes suppress delivery without changing
the underlying incident. Per-reading and power mutes also hide their condition
from Current Problems; System Status remains available. Test mode selects the test recipient list. **Resend
active alert** retries the currently confirmed Danger or missing-reading
alert through the same central dispatcher and therefore respects maintenance
and every mute.

Set `notify_on_service_failure: false` on an individual service in the live
config to suppress its offline and recovery Home Assistant/SMS notifications.
Its service status and confirmed outage remain visible. Reading and power
alarms retain their own policies.

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

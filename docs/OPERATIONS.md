# Operations

The installed source bundle is `~/labpulse-live/config.yaml` plus referenced
measurement files beneath `~/labpulse-live/config.d/`. Edit it with
`labpulse config`, optionally naming one or more source files, so the complete
bundle is validated and `config.resolved.yaml` plus all deployment files are
regenerated. The repository files are only new-install starters.

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
alert through the same central dispatcher. Both delivery paths respect explicit mutes.

Set `notify_on_service_failure: false` on an individual service in the live
config to suppress its offline and recovery Home Assistant/SMS notifications.
Its service status and confirmed outage remain visible. Reading and power
alarms retain their own policies.

A recovery always dismisses the matching persistent Home Assistant problem.
LabPulse creates a recovery notification only when the corresponding opening
notification was created. Every opening SMS request is paired with a recovery
SMS request when the condition resolves and the current global, service, setup,
reading, or power mute allows it.
Changing Test mode before recovery routes the SMS to the current test recipient
list.

## Safe updates

`labpulse update` installs the release, refreshes generated files, and recreates
the whole stack. It runs the new release's `labpulse doctor` after recreation.
There is no separate notification pause or telemetry-readiness gate. Confirmed
outages during an update follow normal confirmation and explicit mute rules.
The SMS worker has a persistent MQTT session: if it is briefly unavailable,
queued QoS 1 failure and recovery requests are delivered in order when it
reconnects, with duplicate request IDs rejected. If Compose fails, fix the
reported problem and use `labpulse up` to start the stack again.

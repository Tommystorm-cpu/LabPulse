# Troubleshooting incidents and notifications

## Service Offline

Inspect the service status and container logs. Offline means the driver is
disconnected, reconnecting, or in an error state; it does not identify a
physical sensor as the cause. One confirmed service incident suppresses
unavailable-reading incidents beneath that service.

## Service Needs attention

The service can still communicate, but it reported a non-online component
status or one of its required readings has no recent usable data. Read the
plain-language explanation on System Status. Valid sibling readings remain
usable.

## No recent data

If the service is Working or Needs attention, inspect the named sensor, wiring,
firmware, source field, and service log. Required readings open one incident
after `missing_confirm_seconds`; readings configured with `required: false`
display **No recent data — optional** and never notify.

Calculated readings are unavailable when a dependency is unavailable or a
division would use zero. Their configured `required` setting applies to the
calculated result.

## No notification was delivered

For a missing persistent Home Assistant notification, check that the incident
was confirmed and that Global Mute and its service, reading, setup, or power
mute allow delivery. SMS worker state does not block these notifications.
For a missing SMS, also check Test mode,
recipient configuration, `sms.dry_run`, and the SMS service log. A recovery SMS
requires an opening SMS request and current notification permission.

## Update failed or SMS worker is offline

Read the update error and inspect `labpulse ps --all` and `labpulse logs
labpulse-sms`. Repair the reported package, setup, or Compose problem, then run
`labpulse up` to start the generated stack. There is no retained update mute to
clear. If the SMS worker was disconnected, queued QoS 1 requests from its
persistent MQTT session may be delivered on reconnect, including a failure and
its recovery close together. Check Test mode and recipient settings before
interpreting where those messages were sent.

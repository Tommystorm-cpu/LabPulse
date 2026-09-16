# Troubleshooting incidents and notifications

## Old LabPulse helpers still appear in History

Recorder exclusions stop new history for LabPulse's internal helpers after the
generated Home Assistant configuration is applied. Existing rows remain until
normal Recorder purging removes them. To remove them immediately, open Home
Assistant **Developer Tools → Actions**, select `recorder.purge_entities`, switch
to YAML mode, and run this optional one-time action:

```yaml
action: recorder.purge_entities
data:
  entity_globs:
    - binary_sensor.labpulse_*_reading_available
    - binary_sensor.labpulse_*_recovery_zone
    - binary_sensor.labpulse_*_service_offline
    - binary_sensor.labpulse_bulk_*
    - sensor.labpulse_*_observed_danger_percent
    - sensor.labpulse_bulk_*
    - input_boolean.labpulse_*
    - input_button.labpulse_*
    - input_datetime.labpulse_*
    - input_number.labpulse_*
    - input_select.labpulse_*
    - automation.labpulse_*
    - script.labpulse_*
```

This deliberately does not match physical or calculated measurement sensors,
or `binary_sensor.labpulse_*_danger_zone`, whose history is required by the
alarm observation window.

## Configuration fragment or resolved runtime fails

Run `labpulse doctor` first. A `measurements_file` must be a relative `.yaml`
or `.yml` path beneath `config.d`, may not use symlinks or `..`, and must contain
a non-empty measurement mapping without a surrounding `measurements:` key.
LabPulse rejects duplicate keys and reports the fragment path for measurement
schema errors. A service must define exactly one of inline `measurements` and
`measurements_file`.

If Doctor reports that `config.resolved.yaml` is missing, stale, or different
from the source bundle, run `labpulse config` and save the guarded edit. Do not
repair the resolved file or Compose mount manually. Real containers mount
`config.resolved.yaml`; fake mode mounts `config.fake.yaml`, which is derived
after resolution.

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

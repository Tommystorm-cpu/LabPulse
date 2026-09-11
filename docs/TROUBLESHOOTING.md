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
display **No recent data — optional** and never notify or block an update.

Calculated readings are unavailable when a dependency is unavailable or a
division would use zero. Their configured `required` setting applies to the
calculated result.

## No notification was delivered

Check update maintenance, Global Mute, the reading or power mute, all affected
setup mutes, Test mode, recipient configuration, `sms.dry_run`, and the SMS
service log. No recovery message is expected when the opening notification was
suppressed.

## Update remains in maintenance

Read the command error first. Home Assistant must receive the retained request
and publish an acknowledgement with the same request ID, and every required
physical reading must publish fresh telemetry. Non-required readings are not part
of this readiness check. After correcting the cause, run:

```bash
labpulse up labpulse-sms
```

This performs the acknowledged maintenance-clear operation before resuming SMS
delivery. Keeping suppression active on failure is deliberate protection
against false outage, recovery, and queued-SMS bursts.

# Troubleshooting incidents and notifications

## Service Offline

Inspect the service status and container logs. Offline means the driver is
disconnected, reconnecting, or in an error state; it does not identify a
physical sensor as the cause. One confirmed service incident suppresses
unavailable-reading incidents beneath that service.

## Service Degraded

The service can still communicate, but it reported a non-online component
status or one of its required readings is not numeric and fresh. Inspect the
Diagnostics reason and each reading's raw state. Valid sibling readings remain
usable.

## Reading unavailable

If service health remains Online or Degraded, inspect the individual MQTT
entity, source field name, parser output, wiring, and firmware. **Reading
unavailable** is intentionally cause-neutral. Required readings open one
incident after `unavailable_confirm_seconds`; optional readings display
**Unavailable — optional** and never notify or block an update.

Calculated readings are unavailable when a dependency is unavailable or a
division would use zero. Their configured availability policy applies to the
calculated result.

## No notification was delivered

Check update maintenance, Global Mute, the reading or power mute, all affected
setup mutes, Test mode, recipient configuration, and `sms.dry_run`. Diagnostics
shows whether Home Assistant created the opening notification and whether it
requested SMS. No recovery message is expected when the opening notification
was suppressed.

## Update remains in maintenance

Read the command error first. Home Assistant must receive the retained request
and publish an acknowledgement with the same request ID, and every required
physical reading must publish fresh telemetry. Optional readings are not part
of this readiness check. After correcting the cause, run:

```bash
labpulse up labpulse-sms
```

This performs the acknowledged maintenance-clear operation before resuming SMS
delivery. Keeping suppression active on failure is deliberate protection
against false outage, recovery, and queued-SMS bursts.


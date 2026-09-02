# Product scope and safety boundary

## Product definition

LabPulse is a laboratory infrastructure **monitoring and alerting aid**. It:

- acquires measurements from configured sensors;
- reports sensor, component, and service health;
- publishes measurements and availability through MQTT;
- presents current and historical state in Home Assistant;
- evaluates configured warning conditions;
- creates operator-facing notifications; and
- exposes explicitly configured, manually operated non-safety GPIO outputs;
- forces controlled outputs toward a configured safe state when software
  command authority is unavailable; and
- provides diagnostics for installation and runtime faults.

LabPulse helps people notice and investigate abnormal conditions. It does not
make equipment safe.

## Safety boundary

LabPulse is not:

- a safety-rated system;
- an emergency shutdown system;
- a machine guard or protective device;
- a fire, gas, oxygen-deficiency, pressure, temperature, or water-flow
  interlock;
- the sole means of detecting a hazardous condition.

LabPulse remains pre-release software. Host crashes, sensor faults, USB or
network failure, broker or Home Assistant failure, configuration mistakes,
mutes, and notification-delivery failures can make monitoring incomplete.
Never rely on LabPulse as the sole detector for a condition that could cause
injury, environmental harm, equipment damage, or substantial financial loss.

## Meaning of monitoring

Monitoring means that LabPulse may:

- read physical or simulated sensor values;
- normalize and label measurements;
- track connection, freshness, and component health;
- store or display observations;
- compare observations with operator-configured thresholds; and
- expose read-only state to documented external integrations.

Measurement drivers publish facts and classified acquisition failures. Output
workers may apply an explicit Home Assistant command to one configured GPIO,
but they do not decide automatically whether equipment may start, continue
operating, or shut down.

## Meaning of alerting

Alerting means that LabPulse may create Home Assistant notifications and SMS
requests when configured conditions are observed. Alerts are **best effort**.

An alert being absent does not establish that conditions are normal. Delivery
success does not establish that a person saw, understood, or acted on the
message. Mutes, test mode, configuration errors, stale data, service failure,
network failure, and third-party delivery failure can all suppress or delay an
alert.

Operators remain responsible for:

- selecting and validating sensors;
- choosing appropriate thresholds and timing;
- testing alarms and delivery paths regularly;
- maintaining recipient and escalation information;
- responding to notifications; and
- providing independent alarms and protective controls where required.

## Equipment control

The controlled-output scope is deliberately narrow: an explicitly enabled
Home Assistant MQTT switch may request logical `ON` or `OFF` from one configured
GPIO output. The output has a configured safe state and may have a maximum
active time. LabPulse publishes GPIO latch readback and availability as command
acknowledgement and records command handling in the worker log.

Commands use one allow-listed topic per output. They are not retained or queued
for an offline worker; retained, malformed, and wrong-topic messages are
rejected. Startup, orderly shutdown, MQTT loss, GPIO failure, and timer expiry
all have defined fail-safe handling. Fake-USB mode omits physical output
workers.

This is not proof that attached equipment moved, and it is not an interlock.
The interface board must establish the safe state without software and provide
appropriate electrical protection. Manual override, position or flow feedback,
and independent local protection remain external responsibilities.

Setpoint changes, automatic alarm-driven actuation, multi-step sequences,
remote public-network control, and safety functions remain outside the current
product scope. Expanding beyond a manual binary output requires a separate risk
assessment, stronger authorization and command-expiry design, audit needs, and
failure-path testing.


## Contribution boundary

Contributions must preserve this separation:

- sensor drivers acquire measurements and health only;
- output drivers implement the separate output lifecycle and never masquerade
  as measurement services;
- the hardware runner owns retry, freshness, and lifecycle behavior;
- Home Assistant owns thresholds and operator-facing alarm state;
- notification workers deliver requests but do not assert receipt or response;
- generic external integration work begins read-only; and
- equipment-command expansion requires an approved control contract rather
  than driver-specific shortcuts.

A proposal that introduces actuation, automatic shutdown, safety claims, or
reliance on LabPulse for hazard mitigation must be discussed before
implementation and must update this document.

## Terminology

In LabPulse documentation:

- **alarm state** means a software state produced from configured observations;
- **alert** or **notification** means a best-effort message about that state;
- **monitoring** means acquiring and presenting facts about equipment;
- **control** means requesting a change to equipment or its operating state;
- **interlock** means an independent protective function that prevents or
  terminates an unsafe condition.

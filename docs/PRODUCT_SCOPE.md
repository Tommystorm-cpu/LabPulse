# Product scope and safety boundary

## Product definition

LabPulse is a laboratory infrastructure **monitoring and alerting aid**. It:

- acquires measurements from configured sensors;
- reports sensor, component, and service health;
- publishes measurements and availability through MQTT;
- presents current and historical state in Home Assistant;
- evaluates configured warning conditions;
- creates operator-facing notifications; and
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
- a substitute for a certified alarm panel;
- a guaranteed notification-delivery service;
- the sole means of detecting a hazardous condition; or
- evidence by itself that equipment or a laboratory is safe to operate.

No person, equipment, experiment, sample, or facility should depend on
LabPulse taking an action within a particular time. A sensor, cable, Raspberry
Pi, power supply, operating system, container, MQTT broker, Home Assistant
automation, network, modem, mobile network, or recipient device can fail or
become unavailable.

Independent protective systems must remain in place wherever a missed,
incorrect, stale, delayed, or duplicated measurement or alert could cause
injury, environmental harm, equipment damage, sample loss, or regulatory
non-compliance.

## Meaning of monitoring

Monitoring means that LabPulse may:

- read physical or simulated sensor values;
- normalize and label measurements;
- track connection, freshness, and component health;
- store or display observations;
- compare observations with operator-configured thresholds; and
- expose read-only state to documented external integrations.

Drivers publish facts and classified acquisition failures. They do not decide
whether equipment may start, continue operating, or shut down.

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

The initial LabPulse product does not command monitored equipment. Drivers read
hardware; Home Assistant evaluates and displays state; the SMS worker delivers
notification requests.

Potential future outputs such as changing a setpoint, acknowledging a device,
starting or stopping equipment, or actuating a relay are outside the initial
product scope. They must not be added by extending the measurement driver
contract or by treating an ordinary MQTT publication as a control command.

Any future control capability requires a separate, explicitly enabled design
with:

- a documented non-safety use case and risk assessment;
- a narrow allow-list of devices and operations;
- separate authentication and authorization from measurement publication;
- command identity, expiry, acknowledgement, audit, and replay protection;
- defined behavior for timeout, restart, stale state, and communication loss;
- manual override and independent local interlocks;
- simulation and failure-path testing; and
- clear user-visible experimental status.

Even with those measures, LabPulse control remains supervisory and non-safety
critical. Safety functions must be implemented independently using equipment
and engineering practices appropriate to the hazard.

## Contribution boundary

Contributions must preserve this separation:

- sensor drivers acquire measurements and health only;
- the hardware runner owns retry, freshness, and lifecycle behavior;
- Home Assistant owns thresholds and operator-facing alarm state;
- notification workers deliver requests but do not assert receipt or response;
- generic external integration work begins read-only; and
- equipment commands require an approved control contract rather than
  driver-specific shortcuts.

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

Calling a Home Assistant state an alarm does not make LabPulse a certified
alarm or safety system.

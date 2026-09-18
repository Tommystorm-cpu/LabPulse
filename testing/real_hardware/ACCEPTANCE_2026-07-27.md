# Raspberry Pi acceptance record: 27 July 2026

This historical summary was preserved from the retired roadmap on
18 September 2026. It records the results reported for revision `dc6c29f` on
the Raspberry Pi 5 Model B Rev 1.1 reference installation. It is not a new
test run or qualification of later releases, replacement hardware, or other
installations. The original summary did not include raw logs here.

## Recorded checks and results

The recorded acceptance covered:

- repeated real-device unplug, reconnect, and recovery;
- DHT11 and X1200 startup, sustained failures, and recovery, including
  injected interface failures;
- container, Home Assistant, and whole-Pi restarts;
- longer UPS outages, restoration, power flapping, and GPIO failure;
- two weeks of continuous operation, including real and simulated sensors;
- real SMS delivery, inbound subscription commands, retry, and recovery
  after modem or service interruption;
- abrupt total power removal and subsequent recovery.

The reported result was that measurements, retained service state, Home
Assistant alarms, and SMS notifications recovered without loss of user-owned
state. Physical defects below were recorded separately from that software
result.

## Hardware limitations found

- Recurring USB disconnects were isolated to a faulty external USB hub, with
  replacement recommended.
- The fitted DHT11 could remain unresponsive after a short power interruption
  and recover only after an extended unpowered period, even though its VCC
  rail fell to approximately `0.014 V`. It was not treated as
  reliability-qualified, and replacement was recommended.

These findings describe the hardware at the time. Use the
[current hardware record](../../docs/HARDWARE.md) and
[main-unit record](../../docs/MAIN_UNIT.md) for later selections and pending
installation work. The July result does not establish the behaviour of the
planned external hub supply or SHT40 connections.

## Watchdog decision at the time

The recorded choice was the Raspberry Pi hardware watchdog through systemd,
with a 30-second runtime timeout. A separate external watchdog was deferred
unless unattended operation demonstrated a failure the internal watchdog
could not recover.

An external power controller would need to account for the X1200 battery
power path; interrupting mains alone would not necessarily turn off the Pi.
See [current watchdog guidance](../../docs/TROUBLESHOOTING.md#host-clock-or-watchdog-warning)
before configuring a deployment.

## Later acceptance

Record subsequent checks with their own date, software revision, hardware,
procedure, result, and limitations. Do not extend this result to a new version
without performing the relevant checks. See
[real-Pi acceptance](../../docs/DEVELOPMENT.md#real-pi-acceptance) and the
[fault-test helpers](README.md).

# MAX17043 UPS Monitoring: Implementation and Live Characterization

## Why this file remains

The Docker refactor now implements the power-monitoring features supported by
the UPS hardware actually installed on the live Pi. Automated and simulated
acceptance was followed by three controlled live-Pi outage/recovery trials.
This file now records the evidence behind the installed transition thresholds
and the remaining post-deployment checks.

## Verified live implementation

The exact background service recovered from the live Pi reads a
MAX17043/MAX17048-compatible fuel gauge on I2C bus 1 at address `0x36`. It uses:

- VCELL register `0x02` for battery voltage;
- SOC register `0x04` for the gauge-calculated state of charge; and
- two 18650 cells arranged as one approximately 3.0-4.2 V battery pack.

The live script explicitly states that current is unsupported. Its published
`0.0 mA` value was a placeholder, not a measurement. Charging status was also
unsupported. Those invented entities are intentionally absent from the
refactor.

## Implemented truthful telemetry

The `max17043_ups` driver:

- opens only the configured `/dev/i2c-N` bus;
- requires the verified address `0x36`;
- performs read-only two-byte register transactions;
- publishes only `voltage` and `battery_level`;
- uses the live script's MAX17043 VCELL and 8.8 fixed-point SOC conversions;
- rejects malformed and physically impossible readings;
- closes a failed bus and retries at the configured reconnect interval; and
- never writes configuration or calibration registers.

Representative live configuration in `~/labpulse-ha/config.yaml`:

```yaml
services:
  ups_monitor:
    enabled: true
    driver: i2c
    i2c_sensor: max17043_ups
    i2c_bus: 1
    i2c_address: 0x36
    device_name: "UPS Monitor"
    display:
      section: "UPS Power"
      icon: "mdi:battery-charging"
      order: 10
    readings:
      - {name: voltage, label: "UPS Battery Voltage", unit: V, device_class: voltage}
      - {name: battery_level, label: "UPS Battery Level", unit: "%", device_class: battery}
    read_interval_seconds: 1
    reconnect_interval_seconds: 5
    power_detection:
      source: ups_transition_inference
      low_voltage_threshold: 4.05
      outage_drop_volts: 0.05
      recovery_rise_volts: 0.062
      transition_window_seconds: 5
      recovery_lockout_seconds: 17
      recovery_charge_rise_percent: null
      recovery_charge_window_seconds: 120
      outage_confirm_seconds: 3
      restore_confirm_seconds: 15
      maximum_reading_age_seconds: 15
```

No battery voltage calibration is required for percentage: the gauge reports
state of charge directly.

## Power inference and its limitation

This HAT does not expose measured current or a confirmed mains-present signal
through the recovered software interface. Controlled live characterization did,
however, find clean separation in short-term voltage transitions:

```text
drop >= 0.050 V in 5 seconds -> possible battery operation
rise >= 0.062 V in 5 seconds -> possible mains recovery
voltage below 4.05 V         -> missed-transition outage fallback
```

The refactor improves the handling of that evidence but cannot improve what it
means. Home Assistant therefore:

- labels the state `Possible On Battery`, never measured mains loss;
- latches a characterized sharp drop and confirms it for 3 seconds;
- latches a characterized rise and confirms it for 15 seconds after a
  17-second battery-rebound lockout;
- records the inferred outage start and duration;
- expires voltage evidence after 15 seconds, then confirms that fault evidence
  for another evidence-age window so routine Home Assistant restarts stay silent;
- reconciles persistent candidate/event state after restart;
- supports an independent power mute; and
- sends validated warning, recovery, fault, and sensor-restored SMS requests.

All dashboard and message wording states that mains is not measured directly.
The absolute threshold cannot declare recovery because unplugged battery voltage
rebounds above it. Optional charge-rise recovery remains disabled until a trial
below 100% SOC produces a defensible threshold.

The preferred future improvement is an electrically isolated mains-present
input. Its normalized evidence should replace `ups_transition_inference` while
retaining the telemetry, dashboard, lifecycle persistence, mute, and SMS
delivery layers.

## Test-Pi simulation

Fake USB uses the same stable service and reading identities as live mode. The
simulator emits voltage and SOC only:

```bash
python3 simulate_serial.py set ups_monitor.power mains
python3 simulate_serial.py set ups_monitor.power battery
python3 simulate_serial.py set ups_monitor.power stale
python3 simulate_serial.py clear ups_monitor.power
```

`stale` stops emission so the real freshness logic is exercised. Simulation
must keep `sms.dry_run: true`.

## Remaining post-deployment acceptance

After deploying the transition-based lifecycle on the live Pi:

1. Keep the legacy power service stopped so only one process accesses/publishes
   the UPS.
2. Confirm `i2cdetect -y 1` still reports `0x36`.
3. Generate Compose and verify only `/dev/i2c-1` is mapped into
   `labpulse-ups-monitor`; it must not be privileged.
4. Start with SMS dry-run and compare voltage/SOC with the old dashboard.
5. Remove the retired fabricated-current MQTT discovery entity once, if it
   exists from an earlier refactor build:

   ```bash
   mosquitto_pub -h 127.0.0.1 -r -n -t homeassistant/sensor/ups_monitor_current/config
   ```

6. Verify container restart and I2C reconnect behaviour.
7. Exercise the fake sharp-drop/rise lifecycle before another controlled
   physical power test.
8. Confirm a real outage produces one warning after the three-second
   confirmation, and restoration produces one recovery only after its
   confirmation and rebound lockout.
9. Confirm the observed post-test settling step below 0.02 V does not trigger
   the production 0.050 V outage threshold.
10. Do not describe the result as direct outage detection.

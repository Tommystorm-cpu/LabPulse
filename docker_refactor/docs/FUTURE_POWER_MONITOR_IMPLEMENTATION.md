# MAX17043 UPS Monitoring: Remaining Live Acceptance

## Why this file remains

The Docker refactor now implements the power-monitoring features supported by
the UPS hardware actually installed on the live Pi. Automated and simulated
acceptance can be completed without that Pi, but the controlled live-Pi run is
still outstanding, so this temporary implementation record must remain.

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
      source: ups_voltage_inference
      low_voltage_threshold: 4.0
      outage_confirm_seconds: 10
      restore_confirm_seconds: 15
      maximum_reading_age_seconds: 15
```

No battery voltage calibration is required for percentage: the gauge reports
state of charge directly.

## Power inference and its limitation

This HAT does not expose measured current or a confirmed mains-present signal
through the recovered software interface. The only currently available power
evidence is the same weak heuristic used by the live service:

```text
battery voltage below configured threshold -> possible battery operation
battery voltage at/above threshold          -> normal inferred state
```

The refactor improves the handling of that evidence but cannot improve what it
means. Home Assistant therefore:

- labels the state `Possible On Battery`, never measured mains loss;
- confirms low voltage continuously for 10 seconds before warning;
- confirms recovery continuously for 15 seconds;
- records the low-voltage event start and duration;
- expires voltage evidence after 15 seconds, then confirms that fault evidence
  for another evidence-age window so routine Home Assistant restarts stay silent;
- reconciles persistent candidate/event state after restart;
- supports an independent power mute; and
- sends validated warning, recovery, fault, and sensor-restored SMS requests.

All dashboard and message wording states that mains is not measured directly.
Returning above the voltage threshold does not prove that mains was restored.

The preferred future improvement is an electrically isolated mains-present
input. Its normalized evidence should replace `ups_voltage_inference` while
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

## Remaining live acceptance

Before enabling this service on the live Pi:

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
7. Exercise a brief below-threshold simulation before any controlled physical
   power test.
8. During a controlled physical test, record how long the battery remains over
   4.0 V after input power is removed. This determines how useful the heuristic
   really is.
9. Do not describe the result as direct outage detection.

When this system is implemented, delete this file

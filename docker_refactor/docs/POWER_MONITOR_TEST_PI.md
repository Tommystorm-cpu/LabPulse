# X1200 power-monitor acceptance on the Raspberry Pi

Use this procedure after deploying the direct GPIO6 implementation. Keep Home
Assistant test mode on and `sms.dry_run: true` until the generated lifecycle and
recipient routing have both been inspected.

## Live configuration

Edit only `~/labpulse-ha/config.yaml`. The UPS service must include:

```yaml
  ups_monitor:
    enabled: true
    driver: i2c
    i2c_sensor: x1200_ups
    i2c_bus: 1
    i2c_address: 0x36
    device_name: "UPS Monitor"
    measurements:
      - {name: voltage, label: "UPS Battery Voltage", unit: V, device_class: voltage}
      - {name: battery_level, label: "UPS Battery Level", unit: "%", device_class: battery}
      - {name: mains_present, label: "External Power Present", state_class: null}
    read_interval_seconds: 1
    reconnect_interval_seconds: 5
    maximum_measurement_age_seconds: 15
    power_detection:
      source: x1200_gpio
      gpio_chip: "/dev/gpiochip0"
      gpio_line: 6
      mains_present_active_high: true
      outage_confirm_seconds: 3
      restore_confirm_seconds: 5
```

## Regenerate and start

```bash
cd ~/labpulse-ha
./generate_compose.sh
./generate_homeassistant_config.sh
sudo docker compose up -d --build
```

Confirm the UPS container has least-privilege device access:

```bash
grep -A20 'labpulse-ups-monitor:' compose.yaml
```

It should list `/dev/i2c-1` and `/dev/gpiochip0`, not privileged mode or the
whole `/dev` directory.

## Verify raw hardware state

With the X1200 input connected:

```bash
sudo gpioget gpiochip0 6
```

Expected: `1`. Disconnect only the low-voltage input to the X1200 while leaving
the Pi running on its batteries. Expected: `0`. Reconnect it and expect `1`.
Never connect or probe mains voltage with Raspberry Pi GPIO equipment.

## Verify MQTT and Home Assistant

Follow the normalized measurements and service status:

```bash
cd ~/labpulse-ha
sudo docker compose exec -T mosquitto mosquitto_sub -v \
  -t 'labpulse/ups_monitor/#'
```

Expected during a controlled test:

1. Connected: `mains_present` is `1`; power state is `Normal`.
2. Disconnect for under three seconds: no warning and no active outage.
3. Disconnect for over three seconds: state becomes `On Battery` and exactly
   one warning request is published.
4. Leave it disconnected: no duplicate warning.
5. Reconnect for under five seconds and interrupt it again: no recovery.
6. Reconnect for over five seconds: state becomes `Normal`, exactly one
   recovery request is published, and duration is recorded.

The Monitor dashboard should continue showing voltage and percentage throughout
the test. Those values are informational; changing them must not create power
events.

## Test-mode recipient safety

In **LabPulse Alarm Setup**, confirm **Test mode** is on. Check container logs:

```bash
sudo docker compose logs --since=10m labpulse-sms
```

Every generated test alert must have `test_mode: true`, a `[TEST]` title, and
only the configured `sms.test_recipients`. The full recipient list must not be
selected. Subscription filtering and the standard unsubscribe footer remain
owned by the SMS worker.

## Fault and restart checks

An unavailable raw mains measurement or `gpio_fault` service status must select
`Sensor Fault`, never `On Battery`. Restore access and confirm the state returns
to the actual current power condition.

During a confirmed outage, restart Home Assistant:

```bash
sudo docker compose restart homeassistant
```

The outage must remain active without a duplicate warning. Reconnect power,
restart Home Assistant during the five-second recovery period, and confirm the
startup reconciliation emits at most one recovery.

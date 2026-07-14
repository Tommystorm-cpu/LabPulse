# UPS Power Monitor: Test-Pi Acceptance Run

This run exercises the complete UPS telemetry and Home Assistant power
lifecycle without an INA219. It uses the `ups_monitor` pseudo-serial device,
the same service name, normalized readings, MQTT identities, dashboard
metadata, and power timings as the live I2C service. SMS remains in dry-run
mode.

The simulator calibration (`3.0 V` empty, `4.2 V` full) is test data only. It
must not be copied to the live Pi.

## 1. Install the current repository build on the test Pi

From the repository checkout:

```bash
cd ~/LabPulse/docker_refactor
mkdir -p "$HOME/labpulse-ha"
cp testing/ups_test_pi_config.yaml "$HOME/labpulse-ha/config.yaml"
LABPULSE_CONTAINER_DIR="$HOME/labpulse-ha" ./setup_container_fs.sh -fake_usb
```

Confirm dry-run SMS before continuing:

```bash
grep -A3 '^sms:' "$HOME/labpulse-ha/config.fake.yaml"
```

The output must contain `dry_run: true`. Do not continue if it does not.

## 2. Start the simulator and inspect its endpoints

```bash
python3 "$HOME/labpulse-ha/simulate_serial.py" start
python3 "$HOME/labpulse-ha/simulate_serial.py" status
ls -l /tmp/labpulse-fake-serial/ups_monitor
```

## 3. Generate and validate Compose and Home Assistant

```bash
cd "$HOME/labpulse-ha"
./generate_compose.sh --config config.fake.yaml -fake_usb
./generate_homeassistant_config.sh --config config.fake.yaml --reset-dashboard
docker compose config
grep -n 'ups_monitor\|power_state\|discharge_evidence' \
  homeassistant/config/packages/labpulse_generated.yaml
```

The `labpulse-ups-monitor` service must mount the fake-serial directory and
`/dev/pts`. It must not be privileged and must not expose `/dev/i2c-1`.

## 4. Start and inspect the stack

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 labpulse-ups-monitor
docker compose logs --tail=100 labpulse-sms
```

Optional MQTT inspection from a host with `mosquitto-clients` installed:

```bash
mosquitto_sub -h 127.0.0.1 -t 'home/sensor/ups_monitor/#' -v
```

Confirm that voltage, signed current, and battery level update approximately
once per second and that the Home Assistant dashboard labels mains state as
inferred from UPS discharge.

## 5. Exercise every power scenario

Start from mains/idle:

```bash
python3 simulate_serial.py set ups_monitor.power mains
```

Select battery operation. The outage candidate should start immediately and
the lifecycle should become `On Battery` only after 10 continuous seconds:

```bash
python3 simulate_serial.py set ups_monitor.power battery
```

Return to mains. The recovery candidate should start immediately and the
lifecycle should return to `Normal` only after 15 continuous seconds. The
recorded duration must run from the first battery evidence to the first
recovery evidence, excluding both confirmation delays:

```bash
python3 simulate_serial.py set ups_monitor.power mains
```

Check charging classification without creating an outage:

```bash
python3 simulate_serial.py set ups_monitor.power charging
```

Stop UPS updates. After 15 seconds without fresh current evidence, the
lifecycle should be `Sensor Fault`:

```bash
python3 simulate_serial.py set ups_monitor.power stale
```

Resume telemetry and verify startup/fault reconciliation:

```bash
python3 simulate_serial.py set ups_monitor.power mains
docker compose restart homeassistant
```

Also test candidate cancellation by selecting `battery` for less than 10
seconds and returning to `mains`; no outage or outage SMS request should be
created.

Toggle the dedicated power mute in **LabPulse Alarm Setup**, repeat a confirmed
battery/recovery cycle, and confirm state/history still change while the SMS
dry-run worker receives no request for the muted transition. Unmute and repeat
to confirm the dry-run request payloads are accepted and logged, never sent.

## 6. Inspect state and dry-run SMS results

```bash
docker compose logs --since=30m labpulse-ups-monitor
docker compose logs --since=30m labpulse-sms
grep -n 'dry_run: true' config.fake.yaml
```

In Home Assistant, inspect these generated entities:

- `input_select.labpulse_ups_monitor_power_state`
- `input_number.labpulse_ups_monitor_power_outage_confirm_seconds`
- `input_number.labpulse_ups_monitor_power_restore_confirm_seconds`
- `input_number.labpulse_ups_monitor_power_maximum_reading_age_seconds`
- `binary_sensor.labpulse_ups_monitor_power_discharge_evidence`
- `binary_sensor.labpulse_ups_monitor_power_sensor_fault`
- `input_boolean.labpulse_ups_monitor_power_muted`
- `sensor.labpulse_ups_monitor_power_last_outage_started`
- `sensor.labpulse_ups_monitor_power_last_outage_duration`

The dashboard uses these read-only template sensors. Their persistent
`input_datetime`/`input_number` backing helpers are intentionally not shown as
editable Monitor controls.

The three timing helpers are shown in **LabPulse Alarm Setup**. They are seeded
once from `power_detection` (10 seconds outage confirmation, 15 seconds
recovery confirmation, and 15 seconds maximum evidence age in this simulator
configuration), then restored by Home Assistant. A candidate snapshots its
confirmation time into its persistent deadline, so changing a setting during a
pending candidate only affects the next candidate.

## 7. Reset and stop simulation

```bash
python3 simulate_serial.py clear ups_monitor.power
python3 simulate_serial.py reset
python3 simulate_serial.py status
docker compose down
python3 simulate_serial.py stop
```

Do not treat this acceptance run as a live-hardware calibration. Before live
deployment, identify the HAT, verify its I2C address/register setup, voltage
scale, signed-current polarity and LSB, battery empty/full voltages, and safe
charging/discharging thresholds.

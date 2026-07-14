# MAX17043 UPS Monitor: Test-Pi Acceptance Run

This run exercises the supported UPS contract without physical I2C hardware:
realistic battery voltage, gauge state of charge, low-voltage inference,
freshness faults, lifecycle persistence, and SMS requests. Current and charging
status are intentionally absent because the live HAT cannot measure them.

Keep SMS in dry-run mode for this entire procedure.

## 1. Prepare the generated test deployment

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh -fake_usb
cd ~/labpulse-ha
```

Confirm the derived config is safe and truthful:

```bash
grep -nE 'dry_run|ups_monitor|Voltage|Battery Level|ups_voltage|low_voltage' config.fake.yaml
grep -nE 'Current|charging_current|discharging_current|ina219' config.fake.yaml && echo "UNEXPECTED OLD POWER FIELD"
```

Generate and inspect Compose and Home Assistant:

```bash
./generate_compose.sh --config config.fake.yaml
./generate_homeassistant_config.sh --config config.fake.yaml --reset-dashboard
grep -n 'labpulse-ups-monitor' compose.yaml
grep -nE 'Possible On Battery|low UPS voltage|low_voltage_evidence' homeassistant/config/packages/labpulse_generated.yaml
```

The fake service must mount `/tmp/labpulse-fake-serial`; it must not receive an
I2C device or privileged mode.

## 2. Start the simulator and containers

```bash
cd ~/LabPulse/docker_refactor
python3 simulate_serial.py start
python3 simulate_serial.py status
ls -l /tmp/labpulse-fake-serial/ups_monitor

cd ~/labpulse-ha
docker compose up -d --build
docker compose logs --tail=100 labpulse-ups-monitor
```

Inspect telemetry directly if `mosquitto-clients` is installed:

```bash
mosquitto_sub -h 127.0.0.1 -t 'home/sensor/ups_monitor/#' -v
```

Only voltage and battery level should be published approximately once per
second. The service status must be online.

## 3. Exercise the lifecycle

Start from normal voltage:

```bash
cd ~/LabPulse/docker_refactor
python3 simulate_serial.py set ups_monitor.power mains
```

Home Assistant should show `Normal`, approximately 4.13 V, and approximately
94.2%.

Test candidate cancellation by selecting low voltage for less than ten seconds:

```bash
python3 simulate_serial.py set ups_monitor.power battery
# wait less than 10 seconds
python3 simulate_serial.py set ups_monitor.power mains
```

No warning or recovery SMS request should be produced.

Confirm a sustained low-voltage event:

```bash
python3 simulate_serial.py set ups_monitor.power battery
```

After ten continuous seconds, the lifecycle should become
`Possible On Battery` and produce exactly one dry-run warning request. Wording
must say that low UPS voltage is the evidence and mains is not measured.

Test recovery cancellation by returning to `mains` for less than 15 seconds,
then selecting `battery` again. No recovery should be sent. Finally select
`mains` continuously for more than 15 seconds. One recovery request should be
produced, and the event duration must use the first low-voltage and first
recovered-voltage evidence times, excluding confirmation delays.

## 4. Exercise stale evidence and reconnect grace

Stop UPS emissions without disconnecting the pseudo-terminal:

```bash
python3 simulate_serial.py set ups_monitor.power stale
```

After the configured maximum evidence age, Home Assistant should enter
`Sensor Fault` and create one persistent notification plus one dry-run SMS
request. Restore telemetry:

```bash
python3 simulate_serial.py set ups_monitor.power mains
```

The fault should clear only after fresh voltage evidence arrives. A persistent
sensor-restored notification and recovery SMS request should be produced.

Now test an actual pseudo-device removal:

```bash
python3 simulate_serial.py disconnect ups_monitor
# reconnect before and after the configured evidence-age grace in separate runs
python3 simulate_serial.py connect ups_monitor
```

Brief reconnect attempts must not create an immediate sensor fault.

## 5. Persistence and mute

Repeat candidate and active-event cases while restarting Home Assistant:

```bash
cd ~/labpulse-ha
docker compose restart homeassistant
```

Test restart during an outage candidate, recovery candidate, and confirmed
low-voltage event. Persistent deadlines must reconcile without duplicate SMS.

Enable the dedicated power mute in LabPulse Alarm Setup, repeat a sustained
low-voltage/recovery cycle, and confirm state/history still update while
notifications and SMS requests are suppressed.

Useful entities include:

- `input_select.labpulse_ups_monitor_power_state`
- `binary_sensor.labpulse_ups_monitor_power_low_voltage_evidence`
- `binary_sensor.labpulse_ups_monitor_power_sensor_fault`
- `input_boolean.labpulse_ups_monitor_power_muted`
- `sensor.labpulse_ups_monitor_power_last_outage_started`
- `sensor.labpulse_ups_monitor_power_last_outage_duration`

## 6. Inspect and reset

```bash
cd ~/labpulse-ha
docker compose logs --since=30m labpulse-ups-monitor labpulse-sms homeassistant

cd ~/LabPulse/docker_refactor
python3 simulate_serial.py clear ups_monitor.power
python3 simulate_serial.py reset
python3 simulate_serial.py status
```

Do not claim live-Pi acceptance from this procedure. The live run must still
confirm the real `0x36` gauge readings and measure how long voltage-based
inference lags behind physical input-power removal.

# Runtime And MQTT

This guide follows one reading from a serial line to a Home Assistant entity.
Use it when debugging missing readings, wrong entity IDs, parser changes, or
dashboard cards that say an entity cannot be found.

## One Sensor Container

Every enabled service in `config.yaml` becomes one Python container.

Example config key:

```yaml
services:
  pressure_monitor:
    enabled: true
```

Generated container:

```text
labpulse-pressure-monitor
```

Container command:

```bash
python main.py --service pressure_monitor
```

The same code runs for every sensor hub. The `--service` value selects the
service-specific config.

## Entry Point Flow

`main.py` owns orchestration:

```text
parse command-line args
configure logging
load config.yaml
select one service
build a driver
connect MQTT publisher unless --no-mqtt is used
connect the driver
publish service status
loop:
  read one serial message
  parse it into readings
  publish status changes
  publish configured readings to MQTT
finally:
  disconnect driver and MQTT client
```

`main.py` should stay boring. It should not contain parser details, Home
Assistant YAML details, threshold logic, or SMS delivery logic.

## Serial Driver

`labpulse_common/drivers/serial_driver.py` owns:

- opening the configured serial path
- reconnecting after failures
- reading raw serial lines
- decoding bytes into text
- calling `SerialParser`
- reporting connection status
- closing the serial handle

The serial path comes from:

```yaml
serial_port: "/dev/serial/by-id/..."
```

or fake USB testing:

```yaml
serial_port: "/tmp/labpulse-fake-serial/pressure"
```

If a serial device disappears, the driver closes the old handle, marks itself
disconnected, and tries again after `reconnect_interval_seconds`.

## Parser Contract

`labpulse_common/parser.py` turns Arduino text into:

```python
dict[str, float]
```

Example pressure line:

```text
0.1034
```

Parser output:

```python
{"pressure": 1.034}
```

The pressure parser treats the Arduino value as MPa and converts to bar:

```text
bar = mpa * 10.0
```

Example labelled line:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/min
```

Parser output:

```python
{"flow1": 2.45, "flow2": 3.10}
```

The parser output keys must match `readings[].name` in `config.yaml`.

## Configured Reading Filter

Before publishing, `HomeAssistantMqttPublisher` filters parser output against
the service config.

If parser output is:

```python
{"flow1": 2.45, "flow2": 3.10, "roomhum": 45.0}
```

and config contains only:

```yaml
readings:
  - name: "flow1"
  - name: "flow2"
```

then `roomhum` is ignored and a warning is logged.

This prevents surprise entities from being created by noisy or malformed serial
data.

## MQTT Topics

LabPulse publishes two kinds of MQTT messages:

1. Home Assistant discovery messages, retained.
2. Current state values.

For service `pressure_monitor` and reading `pressure`:

```text
State topic:
  home/sensor/pressure_monitor/pressure/state

Discovery topic:
  homeassistant/sensor/pressure_monitor_pressure/config
```

For service status:

```text
Status topic:
  home/sensor/pressure_monitor/status

Status discovery topic:
  homeassistant/sensor/pressure_monitor_status/config
```

## MQTT Discovery Payload

For a reading, the discovery payload includes:

```json
{
  "name": "Pressure",
  "state_topic": "home/sensor/pressure_monitor/pressure/state",
  "unique_id": "labpulse_pressure_monitor_pressure",
  "object_id": "labpulse_pressure_monitor_pressure",
  "default_entity_id": "sensor.labpulse_pressure_monitor_pressure",
  "unit_of_measurement": "bar",
  "device_class": "pressure",
  "device": {
    "identifiers": ["pressure_monitor"],
    "name": "Air Pressure Sensor Hub"
  }
}
```

`default_entity_id` is important. It tells Home Assistant the preferred entity
ID to create.

## Stable ID Rules

Stable IDs come from service keys and reading names, not labels.

```text
service_name = pressure_monitor
reading_name = pressure

stable ID = labpulse_pressure_monitor_pressure
entity ID = sensor.labpulse_pressure_monitor_pressure
```

The Home Assistant generator independently predicts the same IDs in:

```text
labpulse_homeassistant/model.py
```

The MQTT publisher generates them in:

```text
labpulse_common/homeassistant_mqtt.py
```

If you change ID rules, update both files and the tests.

## Entity Map

Every Home Assistant generation run writes:

```text
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

Example:

```yaml
pressure_monitor:
  status:
    mqtt_unique_id: labpulse_pressure_monitor_status
    expected_entity_id: sensor.labpulse_pressure_monitor_status
  pressure:
    mqtt_unique_id: labpulse_pressure_monitor_pressure
    expected_entity_id: sensor.labpulse_pressure_monitor_pressure
    alarm_entity_id: binary_sensor.labpulse_pressure_monitor_pressure_alarm
    active_alert: input_boolean.labpulse_pressure_monitor_pressure_alert_active
    minimum_threshold: input_number.labpulse_pressure_monitor_pressure_minimum_threshold
    maximum_threshold: input_number.labpulse_pressure_monitor_pressure_maximum_threshold
    alert_delay: input_number.labpulse_pressure_monitor_alert_delay_seconds
    recovery_delay: input_number.labpulse_pressure_monitor_recovery_delay_seconds
```

Use this file when a dashboard card points at the wrong entity.

## MQTT Debug Commands

Subscribe to everything from the Pi:

```bash
docker run --rm -it --network host eclipse-mosquitto:2 \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t '#' -v
```

Publish a test message:

```bash
docker run --rm --network host eclipse-mosquitto:2 \
  mosquitto_pub -h 127.0.0.1 -p 1883 -t 'labpulse/test/hello' -m 'hello'
```

Watch one service:

```bash
cd ~/labpulse-ha
docker compose logs -f labpulse-pressure-monitor
```

Check persistent logs:

```bash
tail -f ~/labpulse-ha/logs/pressure_monitor.log
```

## Common Failure Chain

If Home Assistant has no entity:

1. Check the service container is running.
2. Check the serial device exists inside the container.
3. Check service logs for parsed readings.
4. Check parser output keys match `readings[].name`.
5. Check MQTT discovery messages are published.
6. Check Home Assistant MQTT integration is connected to `127.0.0.1:1883`.
7. Check `labpulse_entity_map.yaml` for expected entity IDs.

If a reading appears in logs but not Home Assistant, the most common causes are:

- parser key is not listed in `config.yaml`
- Home Assistant MQTT integration has not been added
- MQTT broker address is wrong
- entity was manually renamed in Home Assistant
- dashboard card points at an old entity ID

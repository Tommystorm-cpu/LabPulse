# LabPulse Code Reading Guide

This guide is for understanding the current `docker_refactor/` system well
enough to change it yourself. Read it alongside the code. The aim is not to
memorize every line at once, but to learn the execution paths and the ownership
boundary of each file.

The useful habit is:

```text
For each file:
  What does this file own?
  Who calls it?
  What data shape does it receive?
  What data shape does it return or write?
  What should it never be responsible for?
```

## System Shape

The current system has four main flows:

```text
Setup flow:
  setup_container_fs.sh
    -> ~/labpulse-ha/
    -> generate_compose.sh
    -> generate_homeassistant_config.sh

Sensor flow:
  main.py
    -> config.py
    -> sensor_factory.py
    -> drivers/serial_driver.py
    -> parser.py
    -> homeassistant_mqtt.py
    -> Mosquitto
    -> Home Assistant

Home Assistant generation flow:
  generate_homeassistant_config.sh
    -> labpulse_homeassistant/generator.py
    -> config_io.py
    -> model.py
    -> render.py
    -> templates/

SMS flow:
  Home Assistant automation
    -> MQTT topic labpulse/sms/send
    -> labpulse_sms/sms_entry.py
    -> sms_subscriber.py
    -> sender.py
```

Do not start by reading every file alphabetically. Start with one flow and trace
who calls whom.

## Source Of Truth

On a running Raspberry Pi, the live config is:

```text
~/labpulse-ha/config.yaml
```

In the repo, this file is only a starter template:

```text
docker_refactor/config.yaml
```

Most generated files should be treated as outputs. If something in
`~/labpulse-ha/compose.yaml` looks wrong, change `generate_compose.sh`, not the
generated Compose file by hand.

## Recommended Reading Order

Read in this order:

1. `docker_refactor/config.yaml`
2. `docker_refactor/setup_container_fs.sh`
3. `docker_refactor/generate_compose.sh`
4. `docker_refactor/main.py`
5. `docker_refactor/labpulse_common/config.py`
6. `docker_refactor/labpulse_common/sensor_factory.py`
7. `docker_refactor/labpulse_common/drivers/serial_driver.py`
8. `docker_refactor/labpulse_common/parser.py`
9. `docker_refactor/labpulse_common/homeassistant_mqtt.py`
10. `docker_refactor/generate_homeassistant_config.sh`
11. `docker_refactor/labpulse_homeassistant/generator.py`
12. `docker_refactor/labpulse_homeassistant/config_io.py`
13. `docker_refactor/labpulse_homeassistant/model.py`
14. `docker_refactor/labpulse_homeassistant/render.py`
15. `docker_refactor/labpulse_homeassistant/templates/`
16. `docker_refactor/labpulse_sms/sms_entry.py`
17. `docker_refactor/labpulse_sms/sms_subscriber.py`
18. `docker_refactor/labpulse_sms/sender.py`
19. `docker_refactor/testing/`

After that, read the docs in `docker_refactor/docs/` to compare documented
behavior against implementation.

## Config File

File:

```text
docker_refactor/config.yaml
```

This describes:

- MQTT broker settings.
- SMS backend and recipients.
- Enabled LabPulse services.
- Hardware driver type.
- Serial path and baud rate.
- Parser type.
- Device labels and readings.
- Dashboard display hints.

It should not contain alarm thresholds. Alarm thresholds are owned by Home
Assistant helpers so they can be edited from the dashboard.

Questions to ask while reading:

- Which keys are global?
- Which keys belong to one service?
- Which values are machine-facing IDs?
- Which values are user-facing labels?
- Which values are copied to Home Assistant?

Important distinction:

```yaml
services:
  pressure_monitor:   # stable service key, used in IDs and MQTT topics
    device_name: "Air Pressure Sensor Hub"   # display label
    readings:
      - name: "pressure"   # stable reading key
        label: "Pressure"  # display label
```

Stable keys should change rarely. Labels are safe to edit.

## Setup Flow

File:

```text
docker_refactor/setup_container_fs.sh
```

This is the bootstrap script. It creates or refreshes the live runtime folder:

```text
~/labpulse-ha/
```

It owns:

- Creating the folder structure.
- Copying Python code into `~/labpulse-ha/labpulse-python/`.
- Writing the Dockerfile and requirements file used by Compose.
- Creating Mosquitto config.
- Copying generator scripts.
- Creating a starter `config.yaml` only when the live one is missing.
- Running Compose and Home Assistant config generation.

It should not own:

- Runtime sensor reading.
- MQTT publishing logic.
- Home Assistant alarm logic.
- SMS sending logic.

Read it in chunks:

1. Option parsing.
2. Path variables.
3. Helper functions such as copy/write helpers.
4. Folder creation.
5. Dockerfile creation.
6. Code copying.
7. Config preservation.
8. Generator calls.

The important safety behavior is that the live config and Home Assistant user
state should not be destroyed during ordinary refreshes.

## Compose Generation

File:

```text
docker_refactor/generate_compose.sh
```

This script generates:

```text
~/labpulse-ha/compose.yaml
```

The outer shell handles arguments and file paths. The embedded Python block
parses YAML and writes Compose text.

It owns:

- One Home Assistant container.
- One Mosquitto container.
- One `labpulse-sms` container.
- One Python service container per enabled service.
- Fake USB mounts when testing without real serial devices.
- Real `/dev` mounts when using real serial hardware.
- Extra modem access for the SMS container when `sms.backend: "mmcli"`.

Questions to ask:

- How does it decide which services are enabled?
- How does `-fake_usb` change mounted paths?
- What is shared by all Python containers through `x-labpulse-python-base`?
- Why does Home Assistant use host networking?
- Why does the SMS container get special handling in `mmcli` mode?

Key idea:

```text
Python sensor containers talk to MQTT using service name "mosquitto".
Home Assistant, because it uses host networking, can use 127.0.0.1.
```

## Sensor Runtime Entry Point

File:

```text
docker_refactor/main.py
```

This is the entry point for one sensor service container.

Typical container command:

```text
python main.py --service pressure_monitor
```

Function map:

```text
parse_args()
  Defines CLI flags:
    --config
    --service
    --print
    --no-mqtt
    --once

main()
  Parses args.
  Configures logging.
  Loads config.yaml.
  Selects one service.
  Builds a driver.
  Builds an MQTT publisher unless --no-mqtt is set.
  Connects the driver.
  Publishes service status.
  Loops forever:
    read from driver
    publish status changes
    skip blank readings
    optionally print readings
    publish readings to MQTT
    optionally exit after one reading
  Always disconnects driver and MQTT publisher in finally.
```

When reading `main.py`, follow the variables:

```text
args
config_path
cfg
service_cfg
driver
publisher
readings
current_status
```

`main.py` should stay boring. It orchestrates other components; it should not
parse serial text, decide alarm thresholds, or know Home Assistant YAML details.

## Config Loading

File:

```text
docker_refactor/labpulse_common/config.py
```

This file owns the validated Python shape of `config.yaml`.

Important classes:

```text
MqttConfig
SmsConfig
ReadingConfig
DisplayConfig
ServiceConfig
LabPulseConfig
```

Important functions:

```text
resolve_path()
  Expands and resolves filesystem paths.

resolve_config_relative_path()
  Turns relative config paths into absolute paths based on the config file.

load_config()
  Reads YAML.
  Parses it with PyYAML.
  Validates it with Pydantic.
  Exits with readable errors if config is missing or invalid.

get_service_config()
  Selects one service by name.
  Exits with a useful list if the service name is wrong.

load_recipients()
  Convenience helper for SMS recipients.
```

Read the Pydantic classes as contracts. They define what config values the rest
of the code is allowed to assume exist.

## Sensor Factory

File:

```text
docker_refactor/labpulse_common/sensor_factory.py
```

This file chooses which driver class should be used for a service.

Right now, only serial is implemented:

```text
driver: serial
  -> _build_serial_driver()
  -> SerialDriver(...)
```

GPIO and I2C deliberately raise `NotImplementedError`.

Key function:

```text
_build_serial_driver_config()
```

This converts the broad `ServiceConfig` object into the smaller dict expected
by `serial_driver.py`:

```python
{
    "port": service_config.serial_port,
    "baud_rate": service_config.baud_rate,
    "parser": service_config.parser,
    "reconnect_interval_seconds": service_config.reconnect_interval_seconds,
}
```

This boundary is useful: the serial driver does not need to know every possible
field in `config.yaml`.

## Base Driver Contract

File:

```text
docker_refactor/labpulse_common/sensor_base.py
```

This defines the interface all drivers should follow.

The runtime expects every driver to support:

```text
setup()
read()
get_status()
disconnect()
```

When adding a GPIO or I2C driver later, make it satisfy this same shape so
`main.py` does not need to change.

## Serial Driver

File:

```text
docker_refactor/labpulse_common/drivers/serial_driver.py
```

This file owns the hardware connection to Arduino-style serial devices.

It should own:

- Opening the serial port.
- Reconnecting after failures.
- Reading raw lines.
- Calling `SerialParser`.
- Reporting connection status.
- Disconnecting cleanly.

It should not own:

- Home Assistant MQTT topics.
- Threshold decisions.
- SMS behavior.
- Dashboard naming.

Trace the lifecycle:

```text
Driver.__init__()
  Stores name/config.
  Creates parser.
  Initializes status.

setup()
  Attempts to connect.

read()
  Ensures a connection exists.
  Reads one line.
  Decodes text.
  Sends text to parser.
  Returns dict[str, float] or None.

get_status()
  Returns health/status text.

disconnect()
  Closes the serial connection.
```

When debugging serial issues, check whether the failure is:

- Host device path does not exist.
- Docker did not mount the device path.
- Serial port exists but Arduino sends unexpected text.
- Parser returns `None`.
- Reading names do not match `config.yaml`.

## Parser

File:

```text
docker_refactor/labpulse_common/parser.py
```

This file turns Arduino text into Python dictionaries.

Examples:

```text
"0.67"
  -> {"pressure": 6.7}

"Flow1: 2.4 L/min | Temp0: 20.1C"
  -> {"flow1": 2.4, "temp0": 20.1}
```

Important methods:

```text
parse()
  Selects parser behavior based on parser_type.

_parse_pressure()
  Converts MPa from the pressure Arduino into bar.

_parse_labelled_values()
  Reads labels such as Flow1, Temp0, RoomHum.
  Handles imperfect combined strings like L/minTemp0.

_parse_pipe_delimited()
  Generic fallback parser for label:value chunks.

_key()
  Converts Arduino labels into config reading keys.

_clean_float()
  Extracts the first finite number from a string with units.
```

The output keys from this parser must match `readings[].name` in config.

If the parser returns:

```python
{"flow1": 1.2}
```

then config must contain:

```yaml
readings:
  - name: "flow1"
```

Otherwise `homeassistant_mqtt.py` will ignore that reading as unconfigured.

## MQTT Publisher

File:

```text
docker_refactor/labpulse_common/homeassistant_mqtt.py
```

This file owns Python-to-Home-Assistant MQTT publishing.

It publishes two kinds of MQTT messages:

1. Discovery config, retained, so Home Assistant creates entities.
2. State values, not necessarily retained, so entities update.

Important constants:

```text
DISCOVERY_PREFIX = "homeassistant"
STATE_TOPIC_PREFIX = "home/sensor"
```

Important methods:

```text
connect()
  Connects to MQTT and starts the paho background network loop.

publish(readings)
  Filters readings to configured names.
  Publishes discovery for new readings.
  Publishes current values.

configured_readings(readings)
  Drops values not listed in config.yaml.

publish_status(status)
  Creates and updates a service health entity.

publish_discovery(readings)
  Publishes Home Assistant MQTT discovery payloads.

publish_readings(readings)
  Publishes numeric state values.

state_topic(reading_name)
  Builds the state topic.

discovery_topic(reading_name)
  Builds the discovery topic.

discovery_id(reading_name)
  Builds the stable LabPulse unique/object ID.

default_entity_id(reading_name)
  Builds the expected Home Assistant entity ID.
```

Important ID chain:

```text
service_name = "pressure_monitor"
reading_name = "pressure"

discovery_id:
  labpulse_pressure_monitor_pressure

default_entity_id:
  sensor.labpulse_pressure_monitor_pressure

state_topic:
  home/sensor/pressure_monitor/pressure/state

discovery_topic:
  homeassistant/sensor/pressure_monitor_pressure/config
```

This file is where MQTT discovery identity is controlled. The Home Assistant
dashboard generator independently predicts the same entity IDs, so this file
and `labpulse_homeassistant/model.py` must stay aligned.

## Home Assistant Generator Shell Wrapper

File:

```text
docker_refactor/generate_homeassistant_config.sh
```

This is the shell entry point used on the Pi.

It owns:

- CLI flags such as reset dashboard, backup dashboard, and load dashboard.
- Calling the Python Home Assistant generator.
- Protecting user-editable dashboard behavior.

The Python generator owns the actual model and rendering.

## Home Assistant Generator Entry Point

File:

```text
docker_refactor/labpulse_homeassistant/generator.py
```

This file is intentionally small:

```text
parse args and paths
load LabPulse config
build render model
render files
return exit code
```

It is the Home Assistant equivalent of `main.py`: orchestration, not business
logic.

## Home Assistant Config IO

File:

```text
docker_refactor/labpulse_homeassistant/config_io.py
```

This file owns command-line parsing and YAML loading for the Home Assistant
generator.

It should answer:

- Which config path is being used?
- Which Home Assistant config directory is being written?
- Is dashboard reset enabled?

It should not know how entity IDs are generated.

## Home Assistant Model

File:

```text
docker_refactor/labpulse_homeassistant/model.py
```

This is one of the most important files in the Home Assistant side.

It converts raw `config.yaml` dictionaries into template-friendly dataclasses:

```text
GeneratorPaths
GeneratorOptions
ThresholdModel
ReadingModel
ServiceModel
RenderModel
```

Important helpers:

```text
slug()
  Makes strings safe for Home Assistant IDs.

title()
  Makes a fallback display label.

stable_id()
  Builds stable IDs beginning with labpulse_.

reading_defaults()
  Chooses default helper ranges based on reading names.

build_render_model()
  Converts all enabled services into ServiceModel objects.

build_reading_model()
  Converts one reading into entity IDs and helper IDs.

build_threshold()
  Creates editable default threshold helper settings.
```

Critical idea:

```text
config.yaml owns hardware and labels.
Home Assistant owns alarm values.
```

So `build_threshold()` uses defaults inferred from reading names. It does not
read threshold values from config.

Another critical idea:

```text
stable_id(service_name, reading_name)
```

must match `HomeAssistantMqttPublisher.discovery_id(reading_name)`.

Example:

```text
service_name = pressure_monitor
reading_name = pressure

stable_id:
  labpulse_pressure_monitor_pressure

sensor entity:
  sensor.labpulse_pressure_monitor_pressure

alarm entity:
  binary_sensor.labpulse_pressure_monitor_pressure_alarm

minimum helper:
  input_number.labpulse_pressure_monitor_pressure_minimum_threshold

active-alert memory boolean:
  input_boolean.labpulse_pressure_monitor_pressure_alert_active
```

## Home Assistant Rendering

File:

```text
docker_refactor/labpulse_homeassistant/render.py
```

This file writes actual files into Home Assistant's config folder.

Important functions:

```text
render_all(paths, options, model)
  Creates directories.
  Writes configuration.yaml.
  Writes generated package YAML.
  Writes labpulse_entity_map.yaml.
  Creates UI YAML files if missing.
  Resets or preserves the editable dashboard.

ensure_ui_yaml_files(paths)
  Creates automations.yaml, scripts.yaml, and scenes.yaml if missing.
  Never overwrites them.

write_template(template_name, destination, context)
  Simple placeholder replacement renderer.

entity_map(model)
  Writes a debug map showing MQTT IDs and expected entity IDs.
```

The dashboard preservation behavior is deliberate:

```text
No reset flag:
  preserve Home Assistant editable dashboard

Reset flag:
  seed/reset initial dashboard
```

This keeps the user able to edit the dashboard in Home Assistant.

## Dashboard Builder

File:

```text
docker_refactor/labpulse_homeassistant/dashboard.py
```

This file turns the render model into the initial Lovelace dashboard document.

It is seed behavior only. After the dashboard exists, Home Assistant owns the
editable dashboard unless reset is requested.

If you want to change the default dashboard layout, prefer editing:

```text
docker_refactor/labpulse_homeassistant/templates/dashboard_seed.yaml
```

and only change Python when the template lacks the needed concept.

## Alarm Logic

Files:

```text
docker_refactor/labpulse_homeassistant/alarm.py
docker_refactor/labpulse_homeassistant/templates/alarm_logic.yaml
docker_refactor/labpulse_homeassistant/templates/package.yaml.j2
```

The alarm system is generated into a Home Assistant package.

Home Assistant owns:

- Minimum threshold helpers.
- Maximum threshold helpers.
- Alert delay helpers.
- Recovery delay helpers.
- Binary alarm sensors.
- Active-alert memory booleans.
- Alert/recovery automations.
- MQTT SMS publish actions.

Python sensor services do not decide whether a reading is in alarm. They only
publish readings.

The active-alert memory boolean matters because recovery notifications should
only happen after a real alert was sent. Without that memory, Home Assistant can
emit recovery messages constantly when everything is normal.

## Templates

Folder:

```text
docker_refactor/labpulse_homeassistant/templates/
```

The templates are intentionally readable because they are the best place to
change Home Assistant YAML behavior.

Important files:

```text
configuration.yaml.j2
  Main Home Assistant config include structure.

package.yaml.j2
  Generated LabPulse package wrapper.

alarm_logic.yaml
  Alarm helpers, binary sensors, and automations.

dashboard_seed.yaml
  Rules for the initial editable dashboard.

initial_lovelace.json.j2
  Home Assistant storage document wrapper for the seeded dashboard.

entity_map.yaml.j2
  Debug entity map output.
```

When reading a template, look for placeholders. Those values come from the
model produced by `model.py`.

## SMS Entry Point

File:

```text
docker_refactor/labpulse_sms/sms_entry.py
```

This is the entry point for the SMS container.

Flow:

```text
parse_args()
  Reads --config.

main()
  Configures logging.
  Loads config.
  Builds SMS sender from cfg.sms.
  Creates SMSSubscriber with cfg.mqtt and sender.
  Connects to MQTT.
  Loops forever.
```

It should not parse SMS payload details or run `mmcli` directly. Those jobs
belong to `sms_subscriber.py` and `sender.py`.

## SMS Subscriber

File:

```text
docker_refactor/labpulse_sms/sms_subscriber.py
```

This file owns MQTT subscription for SMS requests.

Important parts:

```text
SMS_TOPIC = "labpulse/sms/#"

SMSSubscriber.__init__()
  Stores MQTT config and sender.
  Creates paho MQTT client.

connect()
  Sets callbacks and connects to broker.

on_connect()
  Subscribes to labpulse/sms/#.

on_message()
  Parses payload.
  Logs alarm identity.
  Formats and broadcasts SMS message.

parse_sms_payload()
  JSON-decodes payloads.
  Falls back to plain text messages.
```

The subscriber does not know whether a message will be logged or sent through
a real modem. That decision belongs to the sender backend.

## SMS Sender

File:

```text
docker_refactor/labpulse_sms/sender.py
```

This file owns delivery backends.

Important pieces:

```text
format_sms_message()
  Converts MQTT payload fields into a readable SMS body.

QueuedSmsSender
  Base class with a worker thread and message queue.
  Serializes sends so the modem is not hit by concurrent requests.

LogSmsSender
  Test backend.
  Logs what would be sent.

MmcliSmsSender
  Real backend.
  Uses ModemManager's mmcli command.

quote_mmcli_value()
  Quotes message/number values for mmcli's parser.

build_sms_sender()
  Chooses backend from sms.backend.
```

Real SMS command flow:

```text
mmcli -L
  Find modem ID.

mmcli -m <modem_id> --messaging-create-sms ...
  Create SMS object in ModemManager.

mmcli -s <sms_path> --send
  Send the created SMS.
```

`mmcli -L` is a debug/sanity command. It is not a required setup command, but
SMS will not work if ModemManager cannot see a modem.

## Tests As Reading Material

Folder:

```text
docker_refactor/testing/
```

Read tests as executable explanations.

Suggested order:

```text
test_parser.py
  What Arduino strings are accepted?

test_sensor_factory.py
  How config chooses drivers.

test_serial_driver.py
  What serial driver setup/read/reconnect promises.

test_homeassistant_mqtt.py
  Exact MQTT topics and discovery payload expectations.

test_homeassistant_entities.py
  Entity ID assumptions.

test_homeassistant_generator.py
  Generated Home Assistant files, dashboard behavior, SMS automation payload.

test_sms_container.py
  SMS container setup, MQTT subscription, payload parsing, sender backends.
```

When you change behavior, update or add the test that describes the new
contract. If a test feels hard to write, the code may be taking on too many
responsibilities at once.

## How To Read One Function

Use this checklist for every function:

```text
1. What are the inputs?
2. Are the inputs raw data, validated config, a model object, or external IO?
3. What side effects happen?
4. What is returned?
5. What errors are expected?
6. What errors should stop the process?
7. Who calls this function?
8. Which test would fail if this function broke?
```

Example with `main.py`:

```text
parse_args()
  Inputs:
    command-line args
  Side effects:
    none
  Return:
    argparse Namespace
  Called by:
    main()
  Tests:
    usually covered indirectly by service/container tests

main()
  Inputs:
    parsed args and config file
  Side effects:
    logging, serial IO, MQTT IO
  Return:
    None, runs until stopped
  Called by:
    Python __main__ guard or Docker command
  Tests:
    behavior covered mostly through smaller unit tests around its dependencies
```

## When Adding A New Sensor

The happy path is:

1. Add a service under `services:` in live `~/labpulse-ha/config.yaml`.
2. Choose `driver: serial` for Arduino USB sensors.
3. Choose or add a parser in `parser.py`.
4. Make sure parsed keys match `readings[].name`.
5. Run parser and MQTT tests.
6. Regenerate Compose if service containers changed:

   ```bash
   cd ~/labpulse-ha
   ./generate_compose.sh
   docker compose up -d --build
   ```

7. Regenerate Home Assistant config if readings/dashboard/alarm entities changed:

   ```bash
   ./generate_homeassistant_config.sh
   ```

Use `--reset-dashboard` only when you want to replace the editable dashboard
with a fresh seed.

## When Adding Alarm Behavior

Prefer changing:

```text
docker_refactor/labpulse_homeassistant/templates/alarm_logic.yaml
```

or related template/model code.

Do not put alarm thresholds into `config.yaml` unless the design changes
deliberately. The current rule is:

```text
Hardware and labels in config.yaml.
Alarm behavior in Home Assistant.
```

For future features such as mute, deadband, re-arm timers, or different recovery
behavior, start by asking:

```text
Can Home Assistant own this with helpers and automations?
```

If yes, add template/model support rather than Python sensor-service logic.

## When Debugging

Use the flow to isolate the layer:

```text
No container:
  check setup_container_fs.sh and compose.yaml

Container starts but no serial:
  check /dev mounts, fake USB mode, serial paths

Serial lines visible but no readings:
  check parser.py and test_parser.py

Readings logged but no Home Assistant entities:
  check homeassistant_mqtt.py discovery topics and MQTT broker

Entities exist but dashboard wrong:
  check labpulse_entity_map.yaml and dashboard seed

Alarm wrong:
  check generated package YAML and alarm_logic.yaml

SMS MQTT received but no text:
  check sms.backend, labpulse-sms logs, ModemManager, mmcli visibility
```

## Useful Commands

Run tests:

```powershell
python .\docker_refactor\testing\test_parser.py
python .\docker_refactor\testing\test_sensor_factory.py
python .\docker_refactor\testing\test_serial_driver.py
python .\docker_refactor\testing\test_homeassistant_mqtt.py
python .\docker_refactor\testing\test_homeassistant_generator.py
python .\docker_refactor\testing\test_sms_container.py
```

Search code:

```powershell
rg "stable_id" docker_refactor
rg "labpulse/sms" docker_refactor
rg "default_entity_id" docker_refactor
```

Inspect generated entity assumptions on the Pi:

```bash
cat ~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

Follow logs:

```bash
cd ~/labpulse-ha
docker compose logs -f labpulse-sms
docker compose logs -f labpulse-pressure-monitor
```

## Learning Milestones

You understand the codebase when you can answer these without searching:

1. Where is the live config on the Pi?
2. Why should generated `compose.yaml` not be hand-edited?
3. How does one service key become one container?
4. How does one Arduino line become a Home Assistant sensor state?
5. What makes Home Assistant entity IDs predictable?
6. Why are alarm thresholds not in `config.yaml`?
7. Why does the dashboard remain editable in Home Assistant?
8. What does the active-alert boolean prevent?
9. How does an alarm become an SMS MQTT message?
10. What is different between `sms.backend: "log"` and `"mmcli"`?

If you can explain those ten points, you can safely make small changes. If you
can also update the matching tests, you can make larger ones.

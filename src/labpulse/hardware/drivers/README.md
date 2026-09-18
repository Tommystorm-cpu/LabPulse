# Hardware drivers

Drivers translate an external interface into LabPulse's numeric reading
contract. Each public module owns a strict option model, driver class,
container-resource function and one `DRIVER_DEFINITION`. Optional hardware
libraries load during connection so configuration and generation work without
hardware.

| Module / ID | Direction | Behaviour |
|---|---|---|
| `serial_pipe.py` / `labpulse.serial_pipe` | Input | Parse unit-free pipe-delimited serial samples |
| `mqtt_json.py` / `labpulse.mqtt_json` | Input | Validate timestamped JSON snapshots and map external names |
| `gpio_input.py` / `labpulse.gpio_input` | Input | Read multiple GPIO lines as named logical `0.0` or `1.0` measurements |
| `gpio_output.py` / `labpulse.gpio_output` | Output | Hold a GPIO line, apply safe state and verify latch readback |
| `dht11.py` / `labpulse.dht11` | Input | Read temperature and humidity with partial-channel faults |
| `sht40.py` / `labpulse.sht40` | Input | Read I2C temperature/humidity and verify both CRCs |
| `x1200.py` / `labpulse.x1200` | Input | Read battery telemetry and mains GPIO |
| `_gpio.py` | Helper | Run `gpioget`, decode state and polarity; not registered |

Serial uses `name:value|name:value` at 9600 baud by default. Units come from
configuration, not the wire. Firmware emits `null` for unavailable channels;
valid fields in a partial sample can continue.

Input drivers may implement `health_status() -> SourceHealth | None` to report
publisher health independently of measurement freshness. The default `None`
uses successful readings to establish health. MQTT JSON uses `WAITING`,
`ONLINE`, and `OFFLINE` when heartbeat monitoring is configured; heartbeats do
not refresh readings or by themselves clear partial-channel faults.

To add a driver, define its typed options, implement idempotent
`connect/read/close`, translate expected boundary failures, declare only the
needed container resources, export one stable definition, and test normal,
invalid, failure and recovery paths. Prefer serial when firmware can normalize
the sensor. Input drivers do not publish LabPulse discovery/state or sleep for
retry; the MQTT input uses a subscription to acquire data. Outputs subclass
`HardwareOutputDriver` and run through `labpulse.output`.

Every `DriverDefinition` requires a container-requirements function, even if
it returns an empty `ContainerRequirements()`. Optional `bind_measurement_sources`
and `bind_measurements` callbacks receive external-name mappings and complete
measurement configuration respectively, during service validation.

GPIO uses a Linux chip and line offset, not a physical header-pin number. Pi
GPIO uses 0 V/3.3 V logic; equipment-specific interfacing is custom to the
eventual hardware.

## Follow registration and a serial read

[`registry.py`](../registry.py) discovers public driver modules at import time
and stores their `DRIVER_DEFINITION` by ID. A
[`DriverDefinition`](../driver.py) connects four things: the ID in config, the
option model that validates it, the class instantiated by the worker, and a
function describing Docker device access. Optional bind callbacks attach
measurement mappings during service validation. Registration opens no devices.

For the simplest input path, read [`SerialPipeDriver`](serial_pipe.py):
`connect()` opens PySerial; `read()` gets one line; `parse_serial_line()` returns
a dictionary; `read()` wraps it in `HardwareReadings`. For example,
`Pressure: 1.2 | temperature: null` becomes `{'pressure': 1.2}`. Invalid fields
are skipped, and the last valid value wins for a repeated name. No usable fields
means `None`, allowing the runner to handle freshness. Port or decoding failure
raises `ConnectionLost`; the runner decides when to reopen it.

## Follow an MQTT input

[`MqttJsonDriver.connect()`](mqtt_json.py) starts Paho's background network loop.
Paho calls `_on_connect()` to subscribe and `_on_message()` when data arrives.
`parse_measurement_message()` checks protocol, timestamp and finite values,
then maps external names to configured stable names. One missing field can
produce a partial `HardwareReadings` with an issue; no usable fields is an error.

The callback writes one pending sample or error under `_message_lock`. The
runner calls `read()` on its own thread to take and clear those slots. Newer
messages replace older pending data: this is a latest-snapshot handoff, not a
history queue. A connection-loss flag takes priority over an invalid-message
error, which takes priority over a sample. The lock keeps each handoff together.

With heartbeat monitoring configured, `health_status()` requires known online
availability and a recent live heartbeat. Retained heartbeats cannot establish health;
reconnection resets the evidence. None of these fields persists to disk.
`close()` marks deliberate shutdown before disconnecting, so the disconnect
callback does not report a new failure, then stops the network thread.

Tests include `test_serial_parser.py`, driver-specific modules and
`test_hardware_factory.py`. See [hardware acquisition](../README.md),
[Configuration](../../../../docs/CONFIGURATION.md) and
[firmware](../../../../firmware/README.md).

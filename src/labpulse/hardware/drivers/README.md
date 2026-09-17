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
the sensor. Inputs do not publish MQTT or sleep for retry. Outputs subclass
`HardwareOutputDriver` and run through `labpulse.output`.

Every `DriverDefinition` requires a container-requirements function, even if
it returns an empty `ContainerRequirements()`. Optional `bind_measurement_sources`
and `bind_measurements` callbacks receive external-name mappings and complete
measurement configuration respectively, during service validation.

GPIO uses a Linux chip and line offset, not a physical header-pin number. Pi
GPIO uses 0 V/3.3 V logic; equipment-specific interfacing is custom to the
eventual hardware.

Tests include `test_serial_parser.py`, driver-specific modules and
`test_hardware_factory.py`. See [hardware acquisition](../README.md),
[Configuration](../../../../docs/CONFIGURATION.md) and
[firmware](../../../../firmware/README.md).

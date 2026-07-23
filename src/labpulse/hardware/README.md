# LabPulse hardware service

This package runs one configured hardware service. Start here before reading the
runner or adding a driver.

## Execution flow

```text
python -m labpulse.hardware --service <name>
  -> cli.py loads config.yaml
  -> registry.py validates options and builds the selected driver
  -> HardwareRunner connects, reads, retries, and tracks freshness
  -> the driver returns normalized ReadingBatch values
  -> HomeAssistantMqttPublisher publishes discovery, state, and service health
```

One process runs one service. Drivers know how to operate hardware; the runner
knows how a long-running service behaves.

## Reading order

1. `cli.py` — composition root for one service process.
2. One driver module such as `drivers/serial_pipe.py`.
3. `api.py` — lifecycle and driver-definition contracts.
4. `registry.py` — automatic discovery of modules under `drivers/`.
5. `runner.py` — retry, scheduling, freshness, status, and cleanup.
6. `homeassistant_publisher.py` — the MQTT boundary.

## Ownership boundary

| Concern | Owner |
| --- | --- |
| Open hardware and convert raw values | Driver |
| Classify an expected hardware failure | Driver |
| Retry and reconnect timing | Runner |
| Read scheduling | Runner |
| Measurement freshness | Runner |
| Service-health status transitions | Runner |
| MQTT discovery and state | Publisher |
| Alarm thresholds and user-facing decisions | Home Assistant |
| Devices, mounts, and container privilege | Driver definition |

Drivers must not sleep for retry intervals, publish MQTT, or implement service
freshness. The runner must not know a sensor protocol or import a hardware
library.

## Driver API

Every driver inherits `BaseSensorDriver` and implements:

```text
connect() -> None
read() -> ReadingBatch | None
close() -> None
```

`ReadingBatch.measurements` maps configured measurement names to finite numeric
values. `None` means that no complete sample is ready yet. A
`ComponentIssue` may accompany valid measurements when only part of a device is
unavailable.

Expected failures use these exceptions:

- `DriverUnavailable`: the initial connection could not be established;
- `ConnectionLost`: an established handle is no longer usable;
- `TransientReadError`: one sample failed but the connection remains usable.

Unexpected exceptions are contained by the runner, logged with a traceback, and
treated as a recoverable service error.

## Runner state machine

```text
disconnected --connect succeeds--> online
      |                            |
      | connect fails              | connection is lost
      v                            v
reconnecting ----------------> disconnected
      |
      +-- retry becomes due --> connect again
```

A transient read error does not close the connection. If valid measurements
remain absent for `maximum_measurement_age_seconds`, status becomes `error`
while reads continue. The next valid batch restores `online`. Cleanup is
idempotent and always attempts to close both the driver and publisher.

## Adding hardware

First decide whether Python code is necessary. An Arduino or other controller
that emits the standard unit-free pipe protocol can use
`labpulse.serial_pipe`; add only configuration, firmware, and simulator coverage.

For a genuinely new direct-hardware driver:

1. Copy `drivers/driver_template.py` to a clearly named module.
2. Keep its options model, `Driver`, builder, resource resolver, and exported
   `DRIVER = DriverDefinition(...)` together in that file.
3. Import optional hardware libraries only inside `connect()` or a helper it
   calls.
4. Add hardware-free lifecycle and Compose-resource tests.
5. Add a service example and update the maintained setup documentation.

The registry discovers the new module automatically. Do not edit the registry,
add device-specific fields to shared `ServiceConfig`, or emit raw Compose YAML.

## Focused tests

```powershell
python .\testing\test_hardware_factory.py
python .\testing\test_hardware_runner.py
python .\testing\test_serial_driver.py
python .\testing\test_dht11_driver.py
python .\testing\test_x1200_ups_driver.py
python .\testing\test_deployment_generation.py
```

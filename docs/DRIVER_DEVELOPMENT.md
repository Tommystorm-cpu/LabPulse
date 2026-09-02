# Driver development

Most new sensors should not require a Python driver. Choose the narrowest
extension path before writing code.

## Choose an extension path

### Configuration-only serial sensor

Use `labpulse.serial_pipe` when an Arduino, microcontroller, or instrument can
emit normalized numeric values in the standard protocol.

You need:

- firmware or device configuration;
- one service entry;
- declared measurements and metadata;
- simulator coverage;
- documentation and a real-device smoke test.

You do not edit the driver registry, runner, publisher, Compose generator, or
Home Assistant generator.

### Direct-hardware driver

Create a driver for GPIO, I2C, SPI, vendor libraries, network APIs, or protocols
that cannot reasonably emit the standard serial format.

### Controlled-output driver

Output drivers are a separate capability. Inherit `HardwareOutputDriver`,
implement the normal `connect/read/close` lifecycle plus `safe_state` and
`set_state(active)`, and configure instances under top-level `outputs`, never
under `services`.

An output `connect()` must acquire the device in its safe state. `set_state()`
must retain ownership and verify the state before returning. `close()` must
attempt the safe state before release and tolerate repeated calls. The shared
output MQTT worker owns command validation, availability, reconnect timing,
maximum-active timing, and Home Assistant discovery; the hardware driver must
not subscribe to MQTT itself.

Physical outputs are omitted in fake-USB mode. Add hardware-free tests for
polarity, atomic safe startup, readback, failed writes, and safe release before
adding any real-device acceptance procedure.

## Driver module structure

Copy:

```text
docs/examples/driver_template.py
```

to a clear public module such as:

```text
src/labpulse/hardware/drivers/bme280.py
```

Keep the same readable order in every driver module:

1. device constants;
2. strict Pydantic `*Config` model;
3. device-specific decoding and dependency helpers;
4. clearly named `*Driver` class;
5. container requirements;
6. exported `DRIVER_DEFINITION`.

The registry discovers public modules automatically. Do not edit
`registry.py`. The contributor template lives in `docs/examples`; helper
modules in the drivers directory must begin with `_` or they will be treated
as drivers.

## Driver configuration

```python
class Bme280Config(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    bus: int = Field(default=1, ge=0)
    address: int = Field(default=0x76, ge=0, le=0x7F)
```

The model owns everything accepted beneath:

```yaml
driver:
  type: example.bme280
  options:
    bus: 1
    address: 0x76
```

Reject unknown fields and unsafe ranges. Normalize only where normalization is
unambiguous. Pydantic is available in host generation and containers.

Do not add device-specific fields to shared `ServiceConfig`.

## Lifecycle contract

Inherit `HardwareDriver` and implement:

```python
def connect(self) -> None: ...
def read(self) -> HardwareReadings | None: ...
def close(self) -> None: ...
```

### Construction

Use the same small constructor shape for every driver:

```python
def __init__(self, service_name: str, config: Bme280Config) -> None:
    super().__init__(service_name)
    self.bus_number = config.bus
    self.address = config.address
    self._device = None
```

Store validated configuration but do not open hardware in `__init__`.
`DriverDefinition` validates the raw mapping before it calls the constructor,
so the driver does not need another `isinstance` check. The registry and tests
must be able to construct a driver without the device.

### Connect

Import optional hardware libraries lazily inside `connect()` or a helper called
from it. Translate missing dependencies and expected initialization failures to
`DriverUnavailable`.

```python
def connect(self) -> None:
    try:
        import vendor_library
        self._device = vendor_library.open(...)
    except (ImportError, OSError) as error:
        self._device = None
        raise DriverUnavailable(f"device unavailable: {error}") from error
```

Never make unrelated services import the vendor library.

### Read

Return configured finite numeric values:

```python
return HardwareReadings(
    {
        "temperature": temperature,
        "humidity": humidity,
    }
)
```

Return `None` when no complete sample is ready. Do not publish MQTT, sleep for
the next poll, or manage reconnect timing.

Use:

- `TransientReadError` when one sample is bad but the handle remains usable;
- `ConnectionLost` when the handle must be closed and recreated;
- `HardwareIssue` with valid measurements when only one component is degraded.

Unexpected programming errors may escape; the runner contains and logs them,
but expected hardware failures should be classified explicitly.

### Close

Release every resource and make repeated calls safe:

```python
def close(self) -> None:
    if self._device is not None:
        self._device.close()
    self._device = None
```

Cleanup must also tolerate partial connection.

## Container resources

Every driver provides one function. For fixed access, ignore the arguments:

```python
def container_requirements(_config: ExampleConfig, _force_simulated: bool) -> ContainerRequirements:
    return ContainerRequirements(mounts=("/dev:/dev",), privileged=True)
```

When access depends on configuration, use it to return the narrowest access:

```python
def container_requirements(
    config: Bme280Config,
    _force_simulated: bool,
) -> ContainerRequirements:
    return ContainerRequirements(
        devices=(f"/dev/i2c-{config.bus}",),
    )
```

`ContainerRequirements` describes three kinds of Docker access:

```python
ContainerRequirements(
    devices=("/dev/i2c-1",),
    mounts=("/host/path:/container/path",),
    privileged=False,
)
```

Prefer individual devices over `/dev:/dev` and avoid `privileged=True` unless
the hardware stack actually requires it. Never return raw Compose YAML.

`force_simulated` lets a definition select fake resources during fake
generation. A driver may also recognize a configured fake path.
`DriverDefinition` passes the same validated configuration type to the driver
and its container-requirements function. The definition always contains a
function; it never contains a mixture of functions and prebuilt results.

## Driver definition

```python
DRIVER_DEFINITION = DriverDefinition(
    driver_id="example.bme280",
    config_model=Bme280Config,
    driver_class=Bme280Driver,
    container_requirements=container_requirements,
    default_read_interval_seconds=1.0,
)
```

Driver IDs are stable public configuration values. Use a namespaced,
lowercase ID and do not reuse an existing ID.

The default interval is used when the service omits
`read_interval_seconds`. Zero is allowed for blocking reads such as the serial
driver; negative values are rejected.

## Measurement contract

Driver reading keys must exactly match the mapping keys under `measurements`.
Unexpected keys are ignored by the publisher.

Drivers publish facts:

- finite numeric values;
- component-health issues;
- connection/read failure classification.

They do not own:

- labels, units, icons, or setup projection;
- alarm thresholds;
- notification decisions;
- Home Assistant entity IDs;
- MQTT topics.

Output drivers are the deliberate exception to the read-only measurement
contract. Their diagnostic `read()` returns `state` as `0.0` or `1.0`, while
commands enter only through the dedicated output worker.

These remain shared configuration and platform concerns.

## Dependencies

Reuse the optional dependency extra for the driver's physical transport. The
currently supported extras are `serial`, `i2c`, and `gpio`; drivers using those
existing transports need no packaging edit. Add a library to the shared
transport extra only when the transport implementation genuinely requires a
new dependency. The root `Dockerfile` installs every supported transport extra
from the release wheel.

System packages belong in the root `Dockerfile` only when required at runtime.
Keep AMD64 and ARM64 support in mind.

## Required tests

Add hardware-free tests covering:

- valid and invalid options;
- driver registry discovery;
- construction without hardware;
- successful connect and reading;
- numeric measurement names and values;
- transient sample failure;
- connection loss;
- missing dependency;
- component issues where applicable;
- repeated cleanup;
- declared Compose resources;
- fake hardware behavior.

Patch the real external boundary: install a small fake optional-library module
in `sys.modules`, or patch `subprocess.run` for a CLI-based device. Do not add
alternate constructors, factories, or command runners to production drivers
for testing. Ordinary tests must not require `/dev`, GPIO, I2C, or network
hardware.

Focused existing examples:

```text
testing/test_serial_driver.py
testing/test_dht11_driver.py
testing/test_x1200_ups_driver.py
testing/test_hardware_factory.py
testing/test_hardware_runner.py
testing/test_deployment_generation.py
```

## Contributor checklist

A driver contribution is ready when it includes:

- self-contained implementation and definition;
- strict documented driver configuration;
- least-privilege resources;
- lazy optional imports;
- hardware-free lifecycle tests;
- simulator or fake where practical;
- example service and measurement configuration;
- documentation updates;
- successful full hardware-free suite;
- real-Pi smoke-test evidence before release.

See [Architecture](ARCHITECTURE.md) for ownership boundaries and
[Configuration](CONFIGURATION.md) for service metadata.

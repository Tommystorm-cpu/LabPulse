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

## Driver module structure

Copy:

```text
src/labpulse/hardware/drivers/driver_template.py
```

to a clear public module such as:

```text
src/labpulse/hardware/drivers/bme280.py
```

Keep these together in that one module:

1. strict Pydantic options model;
2. `Driver` class accepting the service name and typed options;
3. container-resource resolver, only when access depends on options;
4. exported `DRIVER = DriverSpec(...)`.

The registry discovers public modules automatically. Do not edit
`registry.py`. `driver_template.py` is excluded; helper modules in the drivers
directory must begin with `_` or they will be treated as drivers.

## Options model

```python
class Bme280Options(BaseModel):
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

Inherit `BaseSensorDriver` and implement:

```python
def connect(self) -> None: ...
def read(self) -> ReadingBatch | None: ...
def close(self) -> None: ...
```

### Construction

Use the same small constructor shape for every driver:

```python
def __init__(self, name: str, options: Bme280Options) -> None:
    super().__init__(name)
    self.bus = options.bus
    self.address = options.address
    self.device = None
```

Store validated options but do not open hardware in `__init__`. `DriverSpec`
validates the raw mapping before it calls the constructor, so the driver does
not need another `isinstance` check. The registry and tests must be able to
construct a driver without the device.

### Connect

Import optional hardware libraries lazily inside `connect()` or a helper called
from it. Translate missing dependencies and expected initialization failures to
`DriverUnavailable`.

```python
def connect(self) -> None:
    try:
        import vendor_library
        self.device = vendor_library.open(...)
    except (ImportError, OSError) as error:
        self.device = None
        raise DriverUnavailable(f"device unavailable: {error}") from error
```

Never make unrelated services import the vendor library.

### Read

Return configured finite numeric values:

```python
return ReadingBatch(
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
- `ComponentIssue` with valid measurements when only one component is degraded.

Unexpected programming errors may escape; the runner contains and logs them,
but expected hardware failures should be classified explicitly.

### Close

Release every resource and make repeated calls safe:

```python
def close(self) -> None:
    if self.device is not None:
        self.device.close()
    self.device = None
```

Cleanup must also tolerate partial connection.

## Container resources

Declare fixed access directly:

```python
resources=ContainerRequirements(mounts=("/dev:/dev",), privileged=True)
```

When access depends on options, return the narrowest resources from a resolver:

```python
def resources(
    options: Bme280Options,
    _force_simulated: bool,
) -> ContainerRequirements:
    return ContainerRequirements(
        devices=(f"/dev/i2c-{options.bus}",),
    )
```

Available declarations:

```python
ContainerRequirements(
    devices=("/dev/i2c-1",),
    mounts=("/host/path:/container/path",),
    privileged=False,
)
```

Prefer individual devices over `/dev:/dev` and avoid `privileged=True` unless
the hardware stack actually requires it. Never return raw Compose YAML.

`force_simulated` lets a spec select fake resources during fake generation. A
driver may also recognize a configured fake path. `DriverSpec` passes the same
validated options type to the driver and its resource resolver.

## Driver spec

```python
DRIVER = DriverSpec(
    driver_id="example.bme280",
    options_model=Bme280Options,
    implementation=Driver,
    resources=resources,
    default_read_interval_seconds=1.0,
)
```

Driver IDs are stable public configuration values. Use a namespaced,
lowercase ID and do not reuse an existing ID.

The default interval is used when the service omits
`read_interval_seconds`. Zero is allowed for blocking reads such as the serial
driver; negative values are rejected.

## Measurement contract

Driver reading keys must exactly match configured `measurements[].name`.
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

These remain shared configuration and platform concerns.

## Dependencies

Add the optional Python library to an appropriate `pyproject.toml` extra for
development, package users, and the released runtime image. The root
`Dockerfile` installs all supported driver extras from the release wheel.

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
- fake or injected hardware behavior.

Use injected bus/device factories, command runners, or small fake library
objects. Ordinary tests must not require `/dev`, GPIO, I2C, or network hardware.

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

- self-contained implementation and spec;
- strict documented options;
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

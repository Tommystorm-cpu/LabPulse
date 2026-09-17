# Three small changes to learn the code

Work through these on a practice branch after
[setting up your checkout](MAINTAINING.md#1-get-a-working-checkout). They are
exercises, not features you need to add to LabPulse. Start with the dashboard
change; it gives you a visible result with very little code.

## Change a dashboard heading

Suppose you want System Status to say **Recent readings** instead of **Latest
readings**.

1. Open the [System Status template](../src/labpulse/homeassistant/templates/dashboard/system_status.yaml.j2).
   Find `heading: Latest readings` and change that text. Keep entity IDs and
   actions unchanged; this exercise is only about the heading.
2. Run the generation command from
   [the first session](MAINTAINING.md#generate-something-you-can-inspect).
3. Open `testing/tmp/maintainer-demo/homeassistant/config/labpulse-dashboard.yaml`.
   Find the `system-status` view. Its heading should now say `Recent readings`.
4. Run the dashboard tests:

```bash
python -m pytest testing/test_yaml_dashboard.py -q
```

The test `test_system_status_is_human_readable_and_follows_service_ownership`
already generates and parses that view. For a real change, extend its
assertions to cover the intended wording and placement. Don't change an
assertion merely to silence a failure; first check what the failure says about
the result you've generated.

The template is Jinja: text mixed with instructions that produce YAML.
`[[ ... ]]` inserts a value during LabPulse generation; `[% ... %]` controls a
loop or condition. Expressions using `{{ ... }}` and `{% ... %}` belong to
Home Assistant and must remain in the output for it to evaluate later.

To see the change in a browser, regenerate and restart your dedicated
[development installation](DEVELOPMENT.md#host-code-and-runtime-images).
Check both a wide and narrow window. YAML tests won't tell you whether the
heading wraps awkwardly. A real UI change may also need a new screenshot;
update [the capture checklist](../screenshot.md).

## Add a configuration option

The serial driver currently opens its port with a fixed two-second read
timeout. As an exercise, make this configurable as `read_timeout_seconds`.
This option is **not part of the current configuration** unless you implement
the exercise. It belongs to the serial driver, not to every service.

### Carry it from configuration to the device

In [`SerialPipeConfig`](../src/labpulse/hardware/drivers/serial_pipe.py), add:

```python
read_timeout_seconds: float = Field(default=2.0, gt=0, allow_inf_nan=False)
```

In `SerialPipeDriver.__init__`, retain the validated value:

```python
self.read_timeout_seconds = config.read_timeout_seconds
```

In `connect`, replace the fixed timeout argument:

```python
self._serial_connection = serial.Serial(
    self.port, self.baud_rate, timeout=self.read_timeout_seconds
)
```

Once implemented, this fragment belongs under a serial service's `driver`
section. Keep its actual port and other settings:

```yaml
driver:
  type: labpulse.serial_pipe
  options:
    port: /dev/serial/by-id/REPLACE_WITH_YOUR_BOARD
    baud_rate: 9600
    read_timeout_seconds: 1.5
```

The model's default preserves existing behaviour when the field is omitted.
Don't add a special case to the registry or Compose generator: driver options
already travel through the shared configuration path. Check that this new
field survives generation in `config.resolved.yaml`.

### Test the behaviour, not just the field

In [the serial driver tests](../testing/test_serial_driver.py), use the existing
fake serial factory to record the arguments passed to `serial.Serial`.
Assert that the omitted option passes `2.0`, and a configured `1.5` passes
`1.5`. This proves the value reaches the device call; testing only the model
would miss forgetting to use it in `connect`.

Add validation cases rejecting zero, negative, non-finite, and non-numeric
values. In [the configuration tests](../testing/test_config_pipeline.py), load
a complete configuration with the new field and check that an invalid value
identifies the service and driver option in its error.

Run:

```bash
python -m pytest testing/test_serial_driver.py testing/test_config_pipeline.py testing/test_unified_generation.py -q
```

For a real feature, document the default, units, and valid range in the
[serial settings](CONFIGURATION.md#standard-serial-pipe), and add release notes.
Rebuild the runtime image to try it against hardware. Complete simulation
bypasses the serial driver, so it cannot check the new timeout.

## Add a driver without hardware

Use the [counter example](examples/counter_driver.py) to learn the mechanics.
It returns `0.0`, then `1.0`, then `2.0`, and so on when read. It isn't a sensor
or a replacement for LabPulse's normal simulation mode.

### Register it

Copy the example to `src/labpulse/hardware/drivers/example_counter.py` on your
practice branch. Read the file from top to bottom:

- `CounterConfig` validates the starting value and increment.
- `CounterDriver` implements `connect`, `read`, and `close`.
- `container_requirements` returns empty requirements because this example
  doesn't need host hardware.
- `DRIVER_DEFINITION` joins those pieces together under `example.counter`.

The registry discovers public modules in the drivers directory. No list of
driver names needs updating. Helpers that aren't drivers belong in modules
whose names start with `_`.

Make a copy of `docs/examples/minimal-serial.yaml` under `testing/tmp/`. Keep
its MQTT, SMS, and setup sections, and replace its entire `services` section
with this one:

```yaml
services:
  counter:
    label: Practice counter
    driver:
      type: example.counter
      options:
        start: 0.0
        step: 1.0
    measurements:
      count:
        setups: [compressed_air]
        state_class: null
```

Both the returned value key and configured measurement key are `count`. If
they differ, the publisher won't create the reading you expect.

### Exercise the lifecycle

Create `testing/test_example_counter_driver.py` on your practice branch:

```python
import pytest

from labpulse.hardware.driver import ConnectionLost
from labpulse.hardware.drivers.example_counter import CounterConfig
from labpulse.hardware.registry import get_driver_definition


def test_counter_lifecycle():
    definition = get_driver_definition("example.counter")
    driver = definition.create_driver("counter", CounterConfig())
    with pytest.raises(ConnectionLost):
        driver.read()
    driver.connect()
    assert driver.read().values == {"count": 0.0}
    assert driver.read().values == {"count": 1.0}
    driver.close()
    driver.close()
    with pytest.raises(ConnectionLost):
        driver.read()
    driver.connect()
    assert driver.read().values == {"count": 0.0}
```

Run that test, then the existing factory and generation tests. Generate your
practice configuration too, pointing `--config` at your copied YAML. For a
running test, build a new image and use **real mode** on your development host
with only this counter service configured. The counter itself touches no
hardware. Complete fake-hardware mode would substitute its own simulator and
wouldn't execute this example driver.

### Adapt the pattern to a real device

The existing [hardware driver template](examples/driver_template.py) shows the
next pieces: import the optional vendor library during connection, open the
device, and translate expected failures. Use `DriverUnavailable` when opening
fails, `ConnectionLost` when the connection must be recreated, and
`TransientReadError` when one failed read can be retried on the same connection.

Return finite values in the documented units. Use `None` when no usable sample
is ready, and `HardwareIssue` when part of a sample is faulty. Keep retry waits
and MQTT publication in the runner and publisher. Make `close` safe after a
partly failed connection and when called more than once.

Declare required devices or mounts through `ContainerRequirements`. Add any
vendor dependency to the appropriate package extra and ensure the runtime
image installs it. Test connection failure, invalid samples, partial faults,
recovery, resource generation, and cleanup with fakes before testing real
hardware. The counter only teaches the lifecycle; it doesn't cover those
device-specific decisions.

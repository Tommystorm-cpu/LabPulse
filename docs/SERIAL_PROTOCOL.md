# Standard serial protocol

The standard LabPulse serial protocol is the preferred extension interface for
Arduino and other controller-backed sensors. It keeps device-specific code in
firmware and lets the existing `labpulse.serial_pipe` driver handle connection,
parsing, health, MQTT, and Home Assistant.

## Transport

The normal configuration is:

```text
9600 baud
8 data bits
no parity
1 stop bit
newline-delimited UTF-8/ASCII text
```

`baud_rate` is configurable, but firmware and `driver.options.baud_rate` must
match.

Use a stable Linux `/dev/serial/by-id/...` path for real installations.

## Line format

One sample is one newline-terminated line:

```text
name:value|name:value|name:value
```

Examples:

```text
pressure:1.02
temp0:18.4|temp1:19.1|flow1:2.8
voltage:4.08|battery_level:87.0|mains_present:1
```

Rules:

- separate fields with `|`;
- separate a name and value with the first `:`;
- use stable lowercase measurement names;
- emit numeric values without units;
- use a decimal point;
- terminate each sample with `\n`;
- do not emit NaN or infinity;
- emit `null` for an intentionally unavailable value.

The parser trims whitespace and normalizes labels to lowercase, but firmware
should emit the canonical configured spelling.

## Units

The serial stream is unit-free. Units belong in `config.yaml`:

```yaml
measurements:
  - name: temperature
    unit: "°C"
    device_class: temperature
```

Do not emit:

```text
temperature:18.4 C
pressure:1.02 bar
humidity:55%
```

These are not finite numeric values and are ignored.

The firmware, physical sensor calibration, and config must agree on the meaning
of each number. LabPulse publishes the configured unit exactly and does not
convert values.

## Missing and invalid fields

Use:

```text
temp0:18.4|temp1:null|flow1:2.8
```

`null` is intentionally ignored, so other valid fields remain usable.

The parser also ignores:

- fields without `:`;
- empty names;
- empty or non-numeric values;
- NaN and infinity;
- unit-bearing values.

If no field is valid, the line produces no reading batch.

Firmware should prefer an explicit `null` over stale, fabricated, or sentinel
numbers.

## Partial samples

The parser accepts any valid subset of fields in a line. A missing measurement
is not republished from an old sample. If it remains absent beyond
`maximum_measurement_age_seconds`, Home Assistant marks it unavailable.

Where sensors are sampled as one coherent cycle, emit one complete line after
the cycle. Do not split related fields across arbitrary debug lines.

## Measurement names

Every emitted name must be declared under the service's `measurements`.
Undeclared readings are logged and ignored.

Names form long-lived identity. Changing a name changes:

- MQTT topic;
- Home Assistant entity ID;
- alarm helpers;
- history;
- dashboard references.

Use concise lowercase names with letters, numbers, and underscores. Keep debug
text off the measurement stream where possible.

## Repetition and freshness

Publish samples regularly even when the value is unchanged. LabPulse freshness
depends on receiving valid samples, not on numeric changes.

Choose a firmware interval comfortably shorter than the service's
`maximum_measurement_age_seconds`.

## Example configuration

```yaml
services:
  example_monitor:
    enabled: true
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/serial/by-id/usb-example
        baud_rate: 9600
    device_name: "Example Sensor Hub"
    measurements:
      - name: temperature
        label: "Temperature"
        setups: [example_setup]
        unit: "°C"
        device_class: temperature
      - name: pressure
        label: "Pressure"
        setups: [example_setup]
        unit: bar
        device_class: pressure
```

Firmware:

```cpp
Serial.print("temperature:");
Serial.print(temperature);
Serial.print("|pressure:");
Serial.println(pressure);
```

The reusable firmware library provides a pipe sample writer; see
[Firmware](../firmware/README.md).

## Simulator equivalence

`simulate_serial.py` creates pseudo-terminal endpoints and emits the same line
format as real firmware. Parser tests verify simulator payloads.

Use fake mode:

```bash
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
labpulse up --build
```

## Protocol change checklist

A protocol change must update together:

- firmware writers and examples;
- `src/labpulse/hardware/serial_parser.py`;
- simulator payload generation;
- parser and simulator tests;
- starter configuration names;
- this document;
- any affected identity assumptions.

Do not add per-device parser selections or legacy unit-bearing formats. Keep
one simple current protocol.

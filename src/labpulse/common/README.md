# Shared contracts

`labpulse.common` contains definitions that must remain identical across host
generation, sensor workers, Home Assistant, SMS and outputs. It runs wherever
the Python package runs and deliberately has no hardware access.

| File | Contract |
|---|---|
| `config.py` | Central YAML loader, global models, cross-references and source-aware errors |
| `service_config.py` | Driver selection, service timing, measurements and power-service rules |
| `measurement_config.py` | Physical/calculated measurements and restricted formulas |
| `output_config.py` | Output-driver and safe-state configuration |
| `identity.py` | Stable slugs, IDs, titles and Home Assistant entity IDs |
| `mqtt_contracts.py` | Topic constructors and strict SMS requests |
| `fake_config.py` | Preserve the complete resolved fake-hardware runtime document |
| `logging_config.py` | Stdout and optional persistent logging |
| `generated_files.py` | Atomically replace one complete file |
| `sms_templates.py` / `sms_templates.yaml` | Validate and supply notification text |

Unknown fields are rejected. Driver options are converted to the selected
driver's typed model during the central load; consumers should not parse YAML
again. Calculated formulas accept only finite arithmetic and physical inputs.
Single-file replacement is atomic, but replacing several generated files is
not one filesystem transaction.

Keep reusable configuration, identity, topic and small shared utilities here.
Do not add hardware access, CLI parsing, dashboard policy or delivery effects.

## Follow a configuration load

Start at [`load_config()`](config.py). Its normal path is:

1. `_decode_yaml()` reads a mapping and rejects duplicate keys.
2. `_resolve_measurement_files()` expands the selected `config.d` files and
   remembers which service came from which file.
3. `LabPulseConfig.model_validate()` builds the nested models. Pydantic is the
   library that checks field types, fills defaults and calls validators.
4. [`DriverConfig.validate_registered_driver()`](service_config.py) turns each
   options dictionary into the selected driver's model. Then
   `ServiceConfig.validate_hardware_contract()` applies measurement defaults
   and binds source names or GPIO assignments into those options.
5. `LabPulseConfig.validate_cross_references()` checks that the otherwise valid
   sections point to real setups, services and measurements.

The result is a [`ConfigDocument`](config.py):

| Field | What it is for |
|---|---|
| `path` | Resolved master-file path, including when the master text was supplied in memory |
| `source_paths` | Master and referenced files, in read order without repeated paths |
| `measurement_sources` | `(service_name, fragment_path)` pairs for error locations and editing |
| `resolved_data` | Plain YAML data with fragments expanded; used when writing runtime YAML |
| `config` | Validated `LabPulseConfig`, containing defaults and typed nested settings |

For example, `document.config.services['pressure_monitor'].driver.options`
is a `SerialPipeConfig` when that service selects `labpulse.serial_pipe`.
The runner can use its `port` directly without parsing YAML again.

`resolved_data` preserves supplied settings rather than serializing every model
default or private driver binding. `render_resolved_config()` turns it into
standalone YAML; `validate_resolved_config()` loads that text again to check what
workers will receive. Supplying `text=` skips reading the master file, but any
measurement fragments still come from disk relative to the given path.

Input errors become `ConfigError` with `ConfigProblem` locations; the CLI uses
`format_config_error()` to display them. No files are written by `load_config()`.
The document's frozen wrapper does not freeze its inner dictionaries or models:
treat the returned bundle as a read-only snapshot after validation.

## Other data worth knowing

[`MeasurementConfig`](measurement_config.py) describes one physical reading;
`CustomMeasurementConfig` describes arithmetic over physical readings.
`compile_formula()` parses that arithmetic without executing it and returns a
`CompiledFormula`: expression text, referenced names and divisor expressions.
The Home Assistant generator uses those divisors to guard against division by
zero at runtime. Python does not calculate the live result during generation.

[`SmsRequest`](mqtt_contracts.py) is the strict JSON boundary between Home
Assistant and SMS delivery. Topic helpers and [`identity.py`](identity.py)
keep its identifiers aligned with entities and measurement topics. Follow the
[SMS README](../sms/README.md) for what happens after validation.

Relevant tests include `test_config_pipeline.py`, `test_common_contracts.py`,
`test_custom_measurements.py` and `test_deployment_generation.py`. See
[Configuration](../../../docs/CONFIGURATION.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

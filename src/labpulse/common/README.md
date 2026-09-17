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

Relevant tests include `test_config_pipeline.py`, `test_common_contracts.py`,
`test_custom_measurements.py` and `test_deployment_generation.py`. See
[Configuration](../../../docs/CONFIGURATION.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

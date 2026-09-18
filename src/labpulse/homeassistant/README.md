# Home Assistant generation package

This package generates the native Home Assistant dashboard, helpers, derived
entities and alarm automations. It runs on the Pi host during generation and
never reads hardware or delivers SMS.

| Path | Responsibility |
|---|---|
| `generator.py` | Render, validate and install managed files; preserve UI-owned YAML |
| `alarm.py` | Build the common dashboard/alarm render model |
| `templates/` | Final-shaped YAML/Jinja for configuration, dashboards and alarms |
| `__main__.py` | Expose `python -m labpulse.homeassistant` |
| `__init__.py` | Identify the package |

LabPulse manages `configuration.yaml`, `packages/labpulse_generated.yaml` and
`labpulse-dashboard.yaml`. Missing `automations.yaml`, `scripts.yaml` and
`scenes.yaml` are created but existing versions are preserved. Rendered output
is parsed as YAML; guarded configuration also runs Home Assistant's check.

The render model covers physical and calculated measurements, service health,
required/non-required readings, setups, outputs, dashboard grouping,
alarm controls, and stable incident identities. Home Assistant owns thresholds,
missing-reading decisions, confirmation/recovery periods, mutes, Test mode, and
the central notification dispatcher. Hardware services publish facts only; SMS
delivery remains in its owning package.

## Follow generation

Start at [`generate_homeassistant()`](generator.py), called by the deployment
generator or the standalone CLI. It passes `document.config` to
[`build_template_context()`](alarm.py), then renders configuration, alarms and
dashboard from the returned `HomeAssistantRenderModel`. `_render_configuration()`,
`render_alarm()` and `_render_dashboard()` return YAML text. They parse it to
catch structural mistakes before the writer replaces any managed file.

`replace_text()` writes each file individually. `ensure_ui_files()` creates
missing UI files without changing existing ones. Render errors preserve the old
output; a file-write failure can leave only some files replaced. When invoked
by deployment generation, these writes first go into its staging directory.

## What the render model contains

`build_template_context()` first orders setups and assigns outputs, then builds
physical records, calculated records, and the collections used by each view.
It prepares metadata and expression strings; it neither reads live sensor values
nor changes the input config. The model exists for this generation run only.

A physical measurement record looks like this, with unrelated fields omitted:

```python
{
    "service_name": "pressure_monitor",
    "name": "pressure",
    "measurement_id": "pressure_monitor_pressure",
    "entity_id": "sensor.labpulse_pressure_monitor_pressure",
    "setup_ids": ("compressed_air",),
    "blocking_service_names": ("pressure_monitor",),
    # config: the validated MeasurementConfig
    # threshold: limits/step/unit for the threshold editor
}
```

The parent service record holds `name`, `label`, `config`, `measurements`, health
timing and optional `power` metadata. The measurement's `threshold` describes
editor bounds, not the user's current threshold. `blocking_service_names` lets
the alarm defer to a source-service outage. Notification text and mute-expression
strings are prepared here so different views use the same identities and rules.

| Model field | Contents and main use |
|---|---|
| `services` | Physical services; used for health and service-level generation |
| `measurements` | `(service, measurement)` pairs for physical and calculated readings; templates can access both owners without another lookup |
| `alarm_measurements` | Pairs needing ordinary high/low alarms; excludes dedicated power monitoring |
| `power_alarm_services` | Services using the separate composite power-event templates |
| `custom_measurements` / `custom_alarm_services` | Calculated sensor records, and synthetic owners for those with alarms |
| `setups` | Groups with alarm-capable readings, across all dashboards; supplies setup mute helpers |
| `monitor_setups` | All setups assigned to Monitor, including empty ones; supplies cards and measurement blocks |
| `dashboards` | Custom dashboard metadata and their monitor-style setup records |
| `alarm_setup_groups` | Alarm-capable setups grouped by dashboard for the alarm editor |
| `outputs` / `unassigned_outputs` | Switch metadata for all enabled outputs / those with no setup |
| `bulk_alarm_targets` and related fields | Editor choices, affected reading keys, helper IDs, counts and deadband unit groups |

A calculated reading uses a synthetic owner `custom_<id>` and measurement
`value` so it can reuse alarm templates. Its actual sensor is
`sensor.labpulse_custom_<id>`. `source_entities` maps formula aliases to physical
entity IDs; `state_template` and `availability_template` calculate and guard
the value later in Home Assistant. `blocking_service_names` lists its physical
sources, so an input outage takes precedence. There is no synthetic worker.

The builder reuses record dictionaries across these collections. Once it
returns, treat them as read-only: changing one view's record could change
another view too. The frozen dataclass does not freeze those inner dictionaries.

Continue with the [template reading route](templates/README.md) to see how this
data becomes YAML and then live Home Assistant behaviour.

Relevant tests include generator, entity, dashboard, grouping, power and
notification-context suites. See [templates](templates/README.md), the
[User Guide](../../../docs/USER_GUIDE.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

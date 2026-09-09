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
required/optional reading availability, setups, outputs, dashboard grouping,
alarm controls, and stable incident identities. Home Assistant owns thresholds,
availability decisions, confirmation/recovery periods, mutes, Test mode, and
the central notification dispatcher. Hardware services publish facts only; SMS
delivery remains in its owning package.

Relevant tests include generator, entity, dashboard, grouping, power and
notification-context suites. See [templates](templates/README.md), the
[User Guide](../../../docs/USER_GUIDE.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

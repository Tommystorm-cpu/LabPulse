# LabPulse Python package

This directory is the maintained Python implementation. The installed package
supplies commands that run on the Raspberry Pi host and processes that run in
Docker containers.

| Path | Responsibility | Runs in |
|---|---|---|
| `control.py` | Public `labpulse` command: setup, lifecycle, configuration, backup, restore and diagnostics | Pi host |
| `installer.py` | Locate packaged assets and launch the Linux bootstrap | Pi host |
| `backup.py` | Create, validate and restore checksummed state archives | Pi host |
| `doctor.py` | Read-only installation, hardware, Docker and endpoint checks | Pi host |
| `common/` | Configuration, identity, MQTT, logging and file contracts | Host and containers |
| `deployment/` | Generate Compose and staged Home Assistant output | Pi host |
| `hardware/` | Acquire and publish one sensor service | One container per service |
| `homeassistant/` | Generate dashboards, helpers and alarms | Pi host during generation |
| `output/` | Apply MQTT commands to one configured output | One container per output |
| `sms/` | Validate requests and deliver or dry-run SMS messages | SMS container |

`__init__.py` exposes the installed version. Executable subpackages use
`__main__.py` so Compose can run them with `python -m`.

Each process loads the validated configuration independently and coordinates
through MQTT rather than shared Python memory. The operator-owned source is
`~/labpulse-live/config.yaml`; the repository `config.yaml` is only an
installation template.

Configuration is validated at process boundaries. Drivers normalize hardware,
runners own retry and freshness, Home Assistant owns alarm decisions, and SMS
and output workers own their side effects. Do not recreate YAML, identity or
topic rules inside individual services.

Tests are mapped in [`testing/`](../../testing/README.md). Read the
[User Guide](../../docs/USER_GUIDE.md), [Architecture](../../docs/ARCHITECTURE.md)
and [Development guide](../../docs/DEVELOPMENT.md) for cross-package behaviour.

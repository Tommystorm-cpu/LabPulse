# LabPulse Python package

This directory is the maintained Python implementation. The installed package
supplies commands that run on the Raspberry Pi host and processes that run in
Docker containers.

| Path | Responsibility | Runs in |
|---|---|---|
| `control.py` | Public `labpulse` command: setup, lifecycle, configuration, updates, uninstall, backup, restore and diagnostics | Pi host |
| `installer.py` | Locate packaged assets and launch the Linux bootstrap | Pi host |
| `backup.py` | Create, validate and restore checksummed state archives | Pi host |
| `doctor.py` | Read-only installation, hardware, Docker and endpoint checks | Pi host |
| `usb.py` | Interactive USB board identification and stable serial path assignment | Pi host |
| `common/` | Configuration, identity, MQTT, logging and file contracts | Host and containers |
| `deployment/` | Generate Compose and staged Home Assistant output | Pi host |
| `hardware/` | Acquire and publish one sensor service | One container per service |
| `homeassistant/` | Generate dashboards, helpers and alarms | Pi host during generation |
| `output/` | Apply MQTT commands to one configured output | One container per output |
| `sms/` | Validate requests and deliver or dry-run SMS messages | SMS container |

`__init__.py` exposes the installed version. Executable subpackages use
`__main__.py` so Compose can run them with `python -m`.

## Follow a command

Start at [`control.main()`](control.py), which parses the command and selects
its handler. Then choose the route you need:

| Command | Functions to follow | What crosses the boundary |
|---|---|---|
| `setup` | `run_setup()` → [`installer.main()`](installer.py) → [bootstrap](../../deployment/README.md) | Command arguments become a Linux installation and generated files |
| `config` | `run_config_editor()` → `select_config_sources()` → [guarded editor](../../deployment/README.md) | A disposable copy of the source bundle is edited and checked before installation |
| `backup` | `run_backup_command()` → [`create_backup()`](backup.py) → `_assemble_snapshot()` | User-owned files become a checksum manifest and compressed archive |
| `restore` | `run_restore_command()` → `inspect_backup()` → `restore_backup()` → `run_setup()` → `run_compose()` | Checked archive contents replace saved state, then regenerate the deployment |
| `update` | `run_update_command()` → pipx → fresh `labpulse setup` → `run_compose()` | The new package generates and starts its matching deployment |
| `doctor` | [`run_doctor()` → `diagnose()`](doctor.py) | Read-only checks become a report and shell exit status |

Function names in a row belong to `control.py` unless linked elsewhere. The
ordinary sensor path starts in the [hardware package](hardware/README.md);
it doesn't call the host CLI on each reading.

## What a failed command leaves behind

`create_backup()` normally stops only running services, copies/checksums state,
and restarts those services before compression. It also attempts restart after
a copy failure. `quiesce=False` leaves stop/start to the caller. The finished
archive is installed outside the live directory; `force=True` allows replacing
an existing archive.

`restore_backup()` only validates and restores files, with local rollback copies
for replacement failures. The CLI adds service control and a pre-restore archive
of existing user state. Restore or stack-start errors attempt rollback when that
archive exists. The later Home Assistant readiness and doctor checks can return
failure **after restoration has succeeded**; they leave the restored state in
place. Rollback attempts can also fail, and the CLI reports that separately.

Updates install the package first, run its new entry point for generation, then
recreate containers. They do not automatically reinstall the old release on
failure. Read the error's stage before assuming nothing changed. The
[user guide](../../docs/USER_GUIDE.md) covers operator recovery.

Each process loads the validated configuration independently and coordinates
through MQTT rather than shared Python memory. The operator-owned source is
`~/labpulse-live/config.yaml` plus referenced measurement files beneath
`~/labpulse-live/config.d/`; the repository `config.yaml` is only an
installation template. Workers consume the generated resolved configuration.

Configuration is validated at process boundaries. Drivers normalize hardware,
runners own retry and freshness, Home Assistant owns alarm decisions, and SMS
and output workers own their side effects. Do not recreate YAML, identity or
topic rules inside individual services.

Tests are mapped in [`testing/`](../../testing/README.md). Read the
[User Guide](../../docs/USER_GUIDE.md), [Architecture](../../docs/ARCHITECTURE.md)
and [Development guide](../../docs/DEVELOPMENT.md) for cross-package behaviour.

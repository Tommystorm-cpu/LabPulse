# Changelog

All notable user-visible changes will be recorded here. LabPulse is currently
pre-release, and its earlier prototype history was not maintained as formal
releases.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning will follow [Semantic Versioning](https://semver.org/) once release
artifacts are published.

## Unreleased

### Added

- Repository-wide MIT licensing for software, firmware, documentation, and
  hardware design files.
- A reference Raspberry Pi deployment matrix and explicit pre-1.0 support,
  compatibility, safety, and experimental-feature boundaries.
- An explicit product boundary defining LabPulse as monitoring and best-effort
  alerting rather than safety-critical equipment control.
- A pipx-installable `labpulse` package and unified operator command.
- Setup, lifecycle, logs, configuration, browser, firmware-help, and diagnostic
  commands.
- One-container-per-service hardware execution with a central lifecycle runner.
- Self-contained serial, DHT11, and X1200 drivers with declarative resources.
- Hardware-free fake serial devices and controllable alarm scenarios.
- Generated Home Assistant MQTT entities, alarm package, and native YAML
  dashboard.
- Dry-run, test-mode, and modem-backed SMS delivery with subscription controls.

### Changed

- The installed deployment directory is `~/labpulse-live`.
- The guarded configuration command is `labpulse config`.
- Deployment shell scripts are maintained under `deployment/`.
- Measurement units are published exactly as configured while icons are
  derived independently.
- Real-Pi reliability acceptance now records two weeks of continuous operation,
  real and injected hardware faults, UPS and abrupt-power recovery, restart
  alarm reconciliation, SMS delivery, and the built-in watchdog decision.
- `labpulse config` now preserves an active fake-USB deployment and validates
  and regenerates its derived runtime configuration transactionally.
- Hardware lifecycle logs now include stable service/driver/target context,
  status transitions, and the age of the last valid reading.
- `labpulse doctor` now reports the active runtime mode and gives corrective
  commands or checks for common deployment, container, hardware, MQTT, and
  Home Assistant failures.
- `labpulse down` now accepts individual Compose service names, and
  `labpulse restart --build` rebuilds and recreates the complete stack or only
  the selected services.
- Guarded configuration now uses the same configurable Docker command as every
  other lifecycle operation.
- Doctor now checks Docker daemon access and versions, host timezone/NTP state,
  and systemd hardware-watchdog activation.
- Installation now includes ordered Home Assistant/MQTT onboarding, a
  first-install acceptance checklist, host-time validation, and a non-editable
  production update command.

### Removed

- Prototype package layouts and earlier Pi implementations from the active
  runtime. They remain under `legacy/` for reference only.

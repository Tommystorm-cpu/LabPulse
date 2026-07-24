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

### Removed

- Prototype package layouts and earlier Pi implementations from the active
  runtime. They remain under `legacy/` for reference only.

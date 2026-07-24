# Contributing to LabPulse

Thank you for helping improve LabPulse. The project is being prepared for
broader open-source use, but it is still pre-release and its public interfaces
may change.

## Before starting

For a small correction, open a focused pull request. For a new feature,
configuration change, public interface, or hardware driver, open an issue first
so the intended behavior and test boundary can be agreed.

Read:

1. [Architecture](docs/ARCHITECTURE.md)
2. [Development](docs/DEVELOPMENT.md)
3. [Driver development](docs/DRIVER_DEVELOPMENT.md) when adding hardware
4. [Serial protocol](docs/SERIAL_PROTOCOL.md) when changing firmware or serial
   output

## Development principles

- Preserve `~/labpulse-live/config.yaml` as the installed source of truth.
- Keep sensor acquisition in Python and alarm decisions in Home Assistant.
- Prefer the standard serial protocol when firmware can normalize a device.
- Keep optional hardware libraries lazy so unrelated drivers and host-side
  generation do not require them.
- Make important behavior testable without Raspberry Pi hardware.
- Do not add compatibility layers for prototype or `legacy/` behavior unless a
  real released version requires migration.
- Do not commit phone numbers, credentials, Home Assistant state, logs, or
  locally generated deployment files.

## Making a change

1. Create a branch from the current main branch.
2. Install the project in editable mode as described in
   [Development](docs/DEVELOPMENT.md).
3. Make the smallest coherent change.
4. Add or update automated tests.
5. Update the authoritative documentation for changed behavior.
6. Run the complete hardware-free test suite.
7. Describe any real-Pi checks that are still required.

By submitting a contribution, you agree that it may be distributed under the
[MIT License](LICENSE) used by this project.

Do not hand-edit generated `compose.yaml`,
`homeassistant/config/packages/labpulse_generated.yaml`, or
`homeassistant/config/labpulse-dashboard.yaml` as source changes. Update their
generators, models, templates, or source configuration.

## Pull requests

A pull request should explain:

- the problem and intended behavior;
- the components changed;
- automated tests run;
- real hardware tested, if any;
- configuration or generated-output changes;
- documentation updated;
- remaining risks or follow-up work.

Keep unrelated formatting and refactors out of functional changes. Preserve
user changes already present in the branch.

## Hardware contributions

First decide whether the device can emit the unit-free pipe-delimited serial
protocol. If it can, add firmware, configuration, simulator coverage, and
documentation without creating a Python driver.

A direct-hardware driver must include:

- a stable driver ID and strict options model;
- `connect`, `read`, and idempotent `close` behavior;
- normalized numeric readings and classified failures;
- declarative container resources;
- lazy optional dependency imports;
- hardware-free tests for configuration, reading, failure, and cleanup;
- fake or injectable hardware where practical;
- example configuration and documentation;
- a recorded real-device smoke test before release.

See [Driver development](docs/DRIVER_DEVELOPMENT.md).

## Documentation style

Write current facts rather than implementation history. Put operator tasks in
operator guides, cross-component contracts in architecture references, and
code-local details in docstrings. Avoid creating one-off implementation-plan
documents for completed features.

Use relative links inside the repository. Examples must distinguish the
repository starter `config.yaml` from the installed
`~/labpulse-live/config.yaml`.

## Participation

Be respectful, constructive, and professional when opening issues, reviewing
changes, or discussing the project. Do not publish credentials, phone numbers,
private network details, or other sensitive information in issues or pull
requests.

# Supported environments

This document defines the initial LabPulse reference environment and the
support boundaries that apply before version 1.0. A platform is supported only
when it appears in the reference matrix below. Other platforms may work, but
they are not release-qualified until their status is changed here.

## Verified reference deployment

The initial production-like deployment was inventoried on 24 July 2026:

| Component | Verified environment |
|---|---|
| Computer | Raspberry Pi 5 Model B Rev 1.1 with 8 GB RAM |
| Architecture | 64-bit ARM (`aarch64`; Debian `arm64`) |
| Storage | 238.3 GiB MMC block device, approximately 256 GB marketed capacity |
| Operating system | Raspberry Pi OS 64-bit, Debian 12 (Bookworm), reference build 2025-05-13 generated with `pi-gen` stage 4 |
| Host Python | CPython 3.11.2 |
| LabPulse containers | Python 3.12 on the generated Debian slim image |
| Container engine | Docker Engine 29.6.1 |
| Compose | Docker Compose 5.3.1, invoked as `docker compose` |
| Home Assistant | Home Assistant Container 2026.7.2, resolved from the `stable` image tag |
| MQTT broker | Eclipse Mosquitto 2.x in the generated Compose deployment |
| Deployment layout | Generated `~/labpulse-live` Compose project, one container per enabled service |

These are observed reference values, not minimum requirements or broad
compatibility claims. Minimum RAM, storage, Docker Engine, and Compose versions
have not yet been established. A new environment is release-qualified only
after it passes the relevant installation, generation, runtime, and
real-hardware checks.

## Hardware support

### Supported

- Raspberry Pi 5 Model B Rev 1.1 with 8 GB RAM;
- Arduino and other USB serial devices using stable
  `/dev/serial/by-id/...` paths and the LabPulse serial protocol;
- the configured DHT11 GPIO workflow;
- Geekworm X1200 on Raspberry Pi 5 using its MAX17043-compatible I2C telemetry
  and configured mains-detection GPIO;
- fake serial devices supplied by `labpulse setup --fake-usb`.

The X1200 support boundary covers LabPulse monitoring. Battery selection,
charging, physical assembly, power-supply sizing, and safe-shutdown
configuration must follow the hardware manufacturer's instructions.

### Provisional

These environments are reasonable candidates but have not completed the
project's release-qualification workflow:

- other Raspberry Pi 5 revisions and RAM capacities;
- Raspberry Pi 4 Model B, excluding the Pi 5-specific X1200 hardware;
- other Raspberry Pi OS 64-bit Bookworm images, including Lite;
- Raspberry Pi OS 64-bit based on Debian 13 (Trixie);
- other 64-bit Debian-based Linux systems;
- additional serial devices that implement the documented protocol;
- new in-tree drivers before their recorded real-device smoke test.

Problems on provisional environments are welcome as bug reports, but fixes may
require reproduction on the reference deployment.

### Not supported

- 32-bit Raspberry Pi OS or other `armhf`/`armv7` systems;
- Raspberry Pi 3, Zero, Zero 2, Compute Module, or non-Raspberry-Pi hosts;
- third-party GPIO, I2C, SPI, or vendor hardware without a LabPulse driver;
- arbitrary `/dev/ttyUSB0` or `/dev/ttyACM0` identities as permanent
  production configuration;
- hardware or drivers located under `legacy/`.

Unsupported means that the project does not promise installation,
compatibility, diagnosis, or fixes for that environment. It does not mean that
the software is intentionally prevented from running there.

## Software support

### Python

The reference Pi uses CPython 3.11.2. Package metadata and development checks
cover CPython 3.11 and 3.12. LabPulse service containers use Python 3.12
independently of the host interpreter.

Python 3.13 and newer are provisional until they are included in automated
package tests. Python 3.10 and older are unsupported.

### Docker and Compose

The reference Pi uses Docker Engine 29.6.1 and Docker Compose 5.3.1. LabPulse
requires the plugin-style `docker compose` command. The old standalone
`docker-compose` v1 command is unsupported. Minimum compatible Engine and
Compose versions have not yet been established.

Docker Desktop, rootless Docker, Podman, Kubernetes, Home Assistant OS, and
Home Assistant Supervised are outside the current deployment model. LabPulse
runs Home Assistant Container as one service in its own generated Compose
project.

### Home Assistant

The verified reference is Home Assistant Container 2026.7.2, obtained through
the `stable` image tag used by the generated Compose file. Beta, development,
Core-in-a-virtual-environment, Supervised, and Home Assistant OS installations
are not supported deployment targets.

Before LabPulse publishes versioned container images, `stable` is a moving
dependency. A newly published Home Assistant stable release is therefore
provisional until the hardware-free generator suite and the installed Pi have
been checked. Release engineering will replace this moving boundary with a
recorded, reproducible image version.

LabPulse supports its generated native YAML dashboard, MQTT entities, helpers,
and automations. Custom cards, themes, HACS components, and manual edits to
LabPulse-generated Home Assistant files are not supported.

## Supported LabPulse capabilities

The following are the supported pre-1.0 core:

- installation from a repository checkout with pipx;
- generation and operation of `~/labpulse-live`;
- typed configuration through `~/labpulse-live/config.yaml`;
- built-in serial, DHT11, and X1200 measurement acquisition;
- fake-USB simulation;
- MQTT discovery, measurement state, and service health;
- generated Home Assistant dashboards, thresholds, alarms, and mutes;
- read-only diagnostics through `labpulse doctor`;
- dry-run SMS delivery.

These capabilities remain experimental:

- real-modem SMS delivery and inbound subscription commands;
- installation updates between arbitrary repository commits;
- restore and rollback across configuration changes;
- security hardening beyond the documented local deployment boundary;
- external driver or integration packages;
- protocol-level Qubex, Triton, or other external integrations;
- grouped-service deployment;
- equipment commands or other controlled outputs.

Experimental capabilities may be exercised and reported on, but they do not
carry the same compatibility or recovery expectations as the supported core.

## Pre-1.0 compatibility policy

LabPulse is alpha software until the roadmap declares otherwise.

- Minor `0.x` releases may change configuration, generated files, MQTT topics,
  command behavior, or Python interfaces.
- Patch releases should avoid intentional breaking changes.
- Every intentional user-visible break must be documented in the changelog and
  release notes.
- Compatibility and migrations are required only between published releases,
  not between historical prototypes, `legacy/` code, or arbitrary development
  commits.
- Live `config.yaml` and Home Assistant state must not be silently discarded,
  even when an automatic migration is unavailable.
- The external driver API, extension installation command, and equipment
  control contract do not become public compatibility promises until their
  roadmap stages are completed.

Pre-1.0 support means the maintainers will investigate reproducible defects on
the reference environment. It does not promise a response time, long-term
maintenance of every `0.x` release, remote administration, or suitability for
life-safety and equipment-safety functions.

## Safety and network boundary

LabPulse is a monitoring and alerting aid. It is not a safety-rated controller,
shutdown mechanism, or interlock. Independent protective systems remain
necessary wherever equipment failure could cause injury, loss, or damage.

The current generated deployment assumes a trusted private network. Direct
exposure to the public internet or an untrusted shared network is unsupported.
Until the security roadmap is complete, use network isolation, a host or
upstream firewall, and a trusted VPN for remote access.

## Reporting an environment problem

Include:

- Raspberry Pi model and RAM;
- operating-system release and architecture;
- host Python version;
- Docker Engine and Compose versions;
- Home Assistant container version or image digest;
- LabPulse revision or package version;
- enabled driver IDs;
- relevant `labpulse doctor` output and logs with secrets removed.

State whether the environment is supported, provisional, or unsupported under
this document. See [Troubleshooting](TROUBLESHOOTING.md) before reporting a
runtime problem.

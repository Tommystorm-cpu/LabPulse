# Deployment generation package

This package converts one validated configuration into Docker Compose and
generated Home Assistant files. It runs on the Pi host during setup,
configuration changes and restore, not as a long-lived container.

| File | Responsibility |
|---|---|
| `compose.py` | Build deterministic Compose and attach driver-declared resources |
| `generate.py` | Load configuration, stage Home Assistant rendering and install managed output |
| `__main__.py` | Expose `python -m labpulse.deployment` |
| `__init__.py` | Identify the package |

Generation requires an enabled sensor service. Real mode creates one worker per
enabled service and output; fake mode omits physical outputs. Fixed services
are Home Assistant, Mosquitto and SMS. All rendering finishes before live files
are replaced, although several replacements are not one atomic transaction.

Linux installation policy remains in the root [`deployment/`](../../../deployment/README.md),
models in [`common/`](../common/README.md), and template behaviour in
[`homeassistant/`](../homeassistant/README.md). Tests include
`test_deployment_generation.py`, `test_unified_generation.py` and release
generation tests. See [Installation](../../../docs/INSTALLATION.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

# Deployment generation package

This package converts one validated configuration into Docker Compose and
generated Home Assistant files. It runs on the Pi host during setup,
configuration changes and restore, not as a long-lived container.

| File | Responsibility |
|---|---|
| `compose.py` | Build deterministic Compose and attach driver-declared resources |
| `generate.py` | Load configuration, stage Home Assistant rendering and install managed output |
| `mosquitto.py` | Check external MQTT file references and render broker listeners |
| `__main__.py` | Expose `python -m labpulse.deployment` |
| `__init__.py` | Identify the package |

Generation requires an enabled sensor service. Real mode creates one worker per
enabled service and output. Fake mode preserves that worker set, substitutes
in-memory sensors and outputs, removes hardware access, and forces SMS dry-run.
Fixed services are Home Assistant, Mosquitto and SMS. All rendering finishes
before live files are replaced, although several replacements are not one
atomic transaction.

## Follow generation

Start with [`main()` → `generate_deployment()`](generate.py). The combined path
is selected when `--ha-config-dir` is supplied:

1. [`load_config()`](../common/config.py) returns the source `ConfigDocument`.
2. `_runtime_documents()` renders and reloads standalone YAML. It returns the
   resolved text, optional fake text, selected runtime document and mount path.
   The runtime document has the same settings with fragments already expanded.
3. [`validate_external_mqtt_files()`](mosquitto.py) checks configured external
   listener files. [`build_compose()`](compose.py) uses the document, image and
   driver resource declarations to return Compose text without writing it.
4. [`generate_homeassistant()`](../homeassistant/generator.py) writes checked
   Home Assistant YAML beneath a temporary staging directory.
5. `replace_text()` installs the runtime YAML, Compose, broker configuration
   and managed Home Assistant files. The function returns the source document
   and removes its staging directory in `finally`.

A validation or render failure stops before managed live output is replaced.
Once installation begins, each file replacement is atomic: readers see either
the complete old file or complete new file. There is no single transaction over
the whole set, so a later filesystem failure can leave mixed versions. The
generator does not start containers or undo successful earlier replacements.

Without `--ha-config-dir`, `main()` writes runtime YAML, Compose and broker
configuration only. See the [host workflow](../../../deployment/README.md) for
how setup and the guarded editor wrap these functions.

Linux installation policy remains in the root [`deployment/`](../../../deployment/README.md),
models in [`common/`](../common/README.md), and template behaviour in
[`homeassistant/`](../homeassistant/README.md). Tests include
`test_deployment_generation.py`, `test_unified_generation.py` and release
generation tests. See [Installation](../../../docs/INSTALLATION.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

# Controlled output worker

This package runs one configured output in its own container. It is separate
from sensor acquisition because MQTT commands and fail-safe timing have a
different lifecycle.

`__main__.py` selects the output, driver and MQTT client. `service.py` owns
discovery, command parsing, availability, safe-state application, readback,
reconnection and shutdown. `__init__.py` identifies the package.

The worker accepts exact, non-retained `ON` or `OFF` payloads only on its own
topic. It writes the logical state, reads back the GPIO latch, then publishes
retained state. Startup, shutdown, MQTT loss, hardware failure and an optional
maximum-active deadline apply the safe state. Repeated `ON` does not extend an
active deadline. Fake mode omits output workers.

Readback proves the Pi latch, not equipment motion. Pi GPIO uses 0 V/3.3 V;
equipment-specific switching and protection are custom. LabPulse is not a
safety interlock, and automatic alarm-driven actuation is outside this package.

Tests include `test_output_mqtt_service.py`, `test_gpio_output_driver.py` and
dashboard/generation coverage. See [User Guide](../../../docs/USER_GUIDE.md),
[Configuration](../../../docs/CONFIGURATION.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

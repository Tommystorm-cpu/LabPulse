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
active deadline. Fake mode retains output workers and their switches and safety
timers, using an in-memory driver without GPIO access.

## Follow a command

[`main()`](__main__.py) loads one `OutputConfig`, selects its driver and creates
an `OutputMqttService`. In [`service.py`](service.py), read these functions:

1. `run_forever()` registers MQTT callbacks and calls `_maintain_output()` to
   connect hardware in its safe state. It starts Paho's network thread, then
   checks hardware/retry/deadline state every short main-loop wake-up.
2. `on_connect()` subscribes to the output's command topic and publishes its
   discovery, readback and availability.
3. `on_message()` checks the topic and retained flag; `parse_output_command()`
   converts exact `ON`/`OFF` payloads into a boolean. The parser itself cannot
   check MQTT metadata.
4. `_apply_state()` writes through the driver, reads its `HardwareReadings`
   field `state`, and publishes `ON` or `OFF`. It starts a maximum-active
   deadline on an active state if one is configured. Repeated ON leaves an
   existing deadline unchanged.

## Follow failure and shutdown

Paho invokes callbacks on its background network thread while the main loop
runs `_maintain_output()`. `_lock` keeps hardware operations and the associated
readiness/deadline changes together. It is re-entrant, meaning the same thread
can acquire it again. Callers hold it while applying state or reconnecting.

MQTT loss invokes `on_disconnect()` and attempts the safe state. Driver failures
take `_prepare_for_reconnect()`, which closes hardware, clears the deadline and
schedules a retry. A new connection starts safe. `stop()` signals the main loop;
its `finally` calls `close()` to apply safe state, release hardware and stop MQTT.

Timers and readiness flags are not persisted. Retained MQTT state is for the
dashboard, not a saved command to replay. The worker uses a clean subscriber
session and rejects retained commands, so a restart needs a new live command.

Readback proves the Pi latch, not equipment motion. Pi GPIO uses 0 V/3.3 V;
equipment-specific switching and protection are custom. LabPulse is not a
safety interlock, and automatic alarm-driven actuation is outside this package.

Tests include `test_output_mqtt_service.py`, `test_gpio_output_driver.py` and
dashboard/generation coverage. See [User Guide](../../../docs/USER_GUIDE.md),
[Configuration](../../../docs/CONFIGURATION.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

# Hardware acquisition package

This package runs one configured sensor service. Compose starts a separate
container for every enabled service so one failed device does not stop another.

| File | Responsibility |
|---|---|
| `__main__.py` | Select a service and compose its driver, publisher and runner |
| `driver.py` | Reading types, expected failures, lifecycle and resource contracts |
| `registry.py` | Discover and validate driver declarations |
| `runner.py` | Connection, retry, polling, freshness, status and cleanup |
| `homeassistant_publisher.py` | MQTT discovery, readings and retained service status |
| `drivers/` | Supported device and transport implementations |

```text
configuration -> registry -> driver -> runner -> MQTT publisher -> Mosquitto
```

Drivers implement `connect`, `read` and `close` and return normalized numeric
readings. The runner distinguishes unavailable hardware, transient bad samples
and lost connections. By default, a worker becomes online after a valid sample,
and missing data eventually causes reconnection. Drivers can instead report
independent source health through `health_status()`. MQTT JSON heartbeat
monitoring uses this path: the worker waits in `awaiting_heartbeat`, and a
healthy publisher can become online without a new sample. Individual readings
still expire in Home Assistant, and partial driver faults still need attention.
Orderly shutdown closes resources; MQTT Last Will and entity expiry cover
unexpected loss.

## Follow one sample

Open these functions in order. The [pressure walkthrough](../../../docs/MAINTAINING.md#2-follow-one-pressure-reading)
provides a complete example with actual topics and values.

1. [`main()`](__main__.py) loads a `ConfigDocument`, selects a `ServiceConfig`,
   and gets its [`DriverDefinition`](driver.py) from the registry. It creates
   the driver, connects the publisher, then constructs the runner.
2. [`run_forever()` → `step()`](runner.py) either waits, connects, or reads once.
   A step can sleep or block in device I/O; it is not a background task.
3. `_connect()` opens the driver. `_read_and_publish()` later receives
   `HardwareReadings`, for example `values={'pressure': 1.2}`. Missing fields
   are omitted; zero remains a valid value. Optional `HardwareIssue` records
   describe partial faults without throwing away good channels.
4. [`publish()`](homeassistant_publisher.py) filters to configured names,
   creates discovery for new ones, then sends numeric state. The runner
   publishes service status afterward so recovery logic can see the new values.

`RunnerTimings` holds delays and freshness limits. The runner uses a monotonic
clock, which measures elapsed time independently of clock/timezone adjustments.
Its connection flags and timestamps are only in memory. A partial sample
refreshes the batch clock; individual missing measurements still expire in
Home Assistant. Driver data must already be finite and normalized:
`HardwareReadings` is a container for values, not another validator.

## Follow a failure

`DriverUnavailable` during connect schedules another attempt. During reading,
`ConnectionLost` closes the handle and schedules recovery;
`TransientReadError` keeps it open and checks freshness. Empty samples also
take `_handle_missing_readings()`. Without independent source health, stale
data eventually closes and reconnects the driver.

For MQTT inputs with heartbeats, `SourceHealth` supplies a separate answer to
“is the publisher alive?”. A healthy heartbeat can establish service health
without refreshing any numeric reading. See the [driver guide](drivers/README.md)
for the callback-to-runner handoff.

The outgoing publisher also starts a Paho network thread. Its `_on_connect()`
republishes known discovery and status after reconnect; it does not acquire a
new sensor sample. The runner owns normal publication and calls `close()` in
`run_forever()`'s `finally` block. Cleanup closes hardware and disconnects the
publisher; unexpected process loss is covered by MQTT's Last Will and entity
expiry rather than Python cleanup.

Keep acquisition and normalization here. Thresholds and alarms belong to Home
Assistant; SMS and outputs use separate processes. Relevant tests include
`test_hardware_runner.py`, `test_homeassistant_publisher.py`, factory tests and
the driver tests. See [drivers](drivers/README.md), the
[User Guide](../../../docs/USER_GUIDE.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

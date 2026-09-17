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

Keep acquisition and normalization here. Thresholds and alarms belong to Home
Assistant; SMS and outputs use separate processes. Relevant tests include
`test_hardware_runner.py`, `test_homeassistant_publisher.py`, factory tests and
the driver tests. See [drivers](drivers/README.md), the
[User Guide](../../../docs/USER_GUIDE.md) and
[Architecture](../../../docs/ARCHITECTURE.md).

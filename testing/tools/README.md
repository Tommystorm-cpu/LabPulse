# Serial test tools

[`simulate_serial.py`](simulate_serial.py) creates controllable pseudo-serial
devices for testing the serial transport on Linux. It can simulate normal,
out-of-range, stale, disconnected and recovered inputs. Its command interface
is available from the repository root:

```bash
python testing/tools/simulate_serial.py --help
```

Use an activated development environment. For a complete demonstration of
LabPulse, use `labpulse setup --fake-hardware` instead: that mode runs all
configured sensors and outputs in memory and does not need this tool.

The simulator's paths default to `/tmp/labpulse-fake-serial/`. Use it on a
development host, with test configuration and SMS dry-run. The
[`ups_serial.yaml` fixture](../fixtures/ups_serial.yaml) describes a simulated
UPS serial service; it does not configure the real X1200 hardware.

Automated behaviour checks are in
[`test_simulate_serial.py`](../test_simulate_serial.py).

# Real-hardware test helpers

The [27 July 2026 acceptance record](ACCEPTANCE_2026-07-27.md) preserves the
reported results and hardware limitations for that revision. It does not
qualify later releases or replacement devices.

These Linux scripts inject reversible device-access failures into individual
LabPulse containers on a Raspberry Pi:

- `test_x1200_faults.sh` masks the configured X1200 I2C interface, GPIO
  interface, or both;
- `test_dht11_fault.sh` injects an unavailable DHT11 pin before the Adafruit
  driver touches the live GPIO line;
- `hardware_fault_common.sh` provides their shared Compose and recovery
  lifecycle.

`labpulse setup` copies the runnable scripts into `~/labpulse-live`. Run the
installed copies there so they use the live generated `compose.yaml` and
`config.yaml`. See the [user guide](../../docs/USER_GUIDE.md#what-doctor-proves)
for operating boundaries and the [installation troubleshooting section](../../docs/INSTALLATION.md#troubleshooting)
for recovery steps.

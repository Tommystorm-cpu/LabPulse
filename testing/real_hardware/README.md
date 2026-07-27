# Real-hardware test helpers

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
`config.yaml`. See `docs/OPERATIONS.md` for commands and safety notes.

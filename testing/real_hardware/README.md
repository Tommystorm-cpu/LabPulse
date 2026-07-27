# Real-hardware test helpers

These Linux scripts inject reversible device-access failures into individual
LabPulse containers on a Raspberry Pi:

- `test_x1200_faults.sh` masks the configured X1200 I2C interface, GPIO
  interface, or both;
- `test_dht11_fault.sh` masks GPIO interfaces used by a DHT11 service;
- `hardware_fault_common.sh` provides their shared Compose and recovery
  lifecycle.

`labpulse setup` copies the runnable scripts into `~/labpulse-live`. Run the
installed copies there so they use the live generated `compose.yaml` and
`config.yaml`. See `docs/OPERATIONS.md` for commands and safety notes.

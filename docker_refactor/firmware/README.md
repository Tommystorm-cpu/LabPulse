# LabPulse Arduino firmware

This directory contains the standardized firmware for serial Arduinos used by
the Docker refactor. These sketches supersede the human-readable sketches in
the repository-root `Arduino/` directory once each physical board has been
identified, backed up, flashed, and checked.

## Sketch map

| Sketch | Device identity | Readings |
| --- | --- | --- |
| `pressure_monitor/pressure_monitor.ino` | `pressure_monitor` | compressed-air pressure in bar |
| `pump_room/pump_room.ino` | `pump_room` | two flows, four water temperatures, DHT11 room environment, two pressures |
| `turbo_pump/turbo_pump.ino` | `turbo_pump` | two flows and four water temperatures |

All sketches use 9600 baud and emit one compact JSON object per line. They use
the shared `libraries/LabPulseProtocol` Arduino library and avoid dynamic
`String` allocation.

## Serial contract

Startup emits a non-telemetry identity record:

```json
{"device":"turbo_pump","schema":1,"firmware":"turbo-pump-1.0.0","type":"hello"}
```

Each sample has one envelope:

```json
{"device":"turbo_pump","schema":1,"firmware":"turbo-pump-1.0.0","type":"sample","uptime_ms":5000,"readings":{"flow1":0.267,"flow2":0.000,"temp0":18.87,"temp1":18.28,"temp2":null,"temp3":null},"diagnostics":{"sample_ms":5000,"flow1_pulses":10,"flow2_pulses":0,"temp0_adc":512,"temp1_adc":508,"temp2_adc":1023,"temp3_adc":1023}}
```

- `device` must exactly match the service key in `config.yaml`.
- `schema` is the serial contract version, currently `1`.
- `firmware` identifies the flashed sketch revision.
- `readings` contains only values that may be published to Home Assistant.
- An invalid sensor reading is JSON `null`; the Python parser omits it so its
  MQTT entity expires instead of displaying a plausible sentinel value.
- `diagnostics` contains raw pulse/ADC evidence. It is deliberately not
  returned as readings or published as normal Home Assistant telemetry.

The parser rejects a JSON record with a different device or schema. This makes
an incorrect USB-to-service assignment fail visibly instead of silently
publishing one Arduino's values under another device.

## Pin map retained from the existing sketches

| Device | Function | Arduino pin |
| --- | --- | --- |
| pressure monitor | pressure analog input | A0 |
| pump room | flow 1 / flow 2 | D3 / D2 |
| pump room | DHT11 | D4 |
| pump room | water temperatures 0-3 | A0-A3 |
| pump room | pressure 1 / pressure 2 | A5 / A4 |
| turbo pump | flow 1 / flow 2 | D2 / D3 |
| turbo pump | water temperatures 0-3 | A0-A3 |

The pump-room and turbo-pump flow order is intentionally different because
that is what their existing sketches declare. Verify the PCB and cable wiring
before flashing rather than assuming those labels are physically correct.

## Reliability changes

The flow sketches:

- increment `volatile unsigned long` counters in minimal interrupt handlers;
- copy and reset both counters atomically;
- leave the flow interrupts attached while sensor reads and serial output run;
- calculate litres/minute outside the interrupt;
- include raw pulse counts and the measured sample interval in diagnostics.

Thermistor inputs reject ADC endpoint values before divider and logarithm
calculations. Calculated values must also be finite and within a broad physical
sanity range. The pressure and DHT inputs apply equivalent finite/range checks.

Zero pulses still cannot distinguish a stationary connected flow sensor from a
missing or disconnected one. Physical flow or an injected test pulse remains
necessary to prove that channel.

## Build prerequisites

The target used by the existing installation is expected to be an Arduino Uno.
Install:

- the Arduino AVR Boards core;
- this directory's `LabPulseProtocol` library;
- the Arduino `DHT sensor library` for the pump-room sketch only.

Example Arduino CLI commands from `docker_refactor/firmware`:

```bash
arduino-cli compile --fqbn arduino:avr:uno \
  --libraries ./libraries pressure_monitor

arduino-cli compile --fqbn arduino:avr:uno \
  --libraries ./libraries turbo_pump

arduino-cli compile --fqbn arduino:avr:uno \
  --libraries ./libraries pump_room
```

Do not flash a live board until its stable `/dev/serial/by-id/...` identity,
physical role, current sketch, and pin wiring have been recorded. Flash one
board at a time, read its `hello` line, verify every configured reading, and
then run its LabPulse container.

# LabPulse Arduino firmware

These are the standard serial sketches for the Docker refactor. Each sketch is
self-contained so a lab can copy the nearest example, change its pins and
calibration constants, and add or remove labelled values without learning a
custom protocol library.

## Serial contract

All sketches use 9600 baud and emit one complete sample per line:

```text
key: value | key: value | key: value
```

For example:

```text
pressure: 1.03
flow1: 2.45 | flow2: 3.10 | temp0: 20.11 | temp1: 20.22
```

Rules:

- keys are lower-case and exactly match `measurements[].name` in `config.yaml`;
- each value is already in the unit declared by config;
- units are not written into the serial line;
- invalid sensor channels are written as `null` and ignored by Python;
- sketches do not emit JSON, startup records, or diagnostics records;
- serial services use the generic `parser: pipe` parser.

The contract deliberately has no device identity field. Stable
`/dev/serial/by-id/...` assignments identify boards, so operators must verify
the physical board-to-service mapping before flashing.

## Sketch map

| Sketch | Measurements | Interval |
| --- | --- | --- |
| `pressure_monitor/pressure_monitor.ino` | compressed-air pressure in bar | 1 s |
| `pump_room/pump_room.ino` | two flows, four water temperatures, room DHT11, two pressures | 5 s |
| `turbo_pump/turbo_pump.ino` | two flows and four water temperatures | 5 s |

## Legacy-equivalent pins and calculations

The refactor sketches retain the installed sketches' pins, calibration values,
equations, and displayed precision.

| Device | Function | Pins / calibration |
| --- | --- | --- |
| pressure monitor | pressure | A0; 0.48-4.5 V = 0-1.6 MPa; ADC divisor 1023 |
| pump room | flow 1 / flow 2 | D3 / D2; 450 pulses per litre |
| pump room | temperatures | A0-A3; 4.7 kOhm divider and original Steinhart-Hart coefficients |
| pump room | room / pressure | DHT11 on D4; pressure 1 / 2 on A5 / A4 |
| turbo pump | flow 1 / flow 2 | D2 / D3; 450 pulses per litre |
| turbo pump | temperatures | A0-A3; 4.7 kOhm divider and original Steinhart-Hart coefficients |

The pump-room pressure calculation intentionally retains its legacy
`5.0 / 1024.0` ADC scaling and zero clamp. The standalone pressure sketch now
performs the MPa-to-bar conversion itself, but first preserves the old sketch's
four-decimal MPa quantisation. The published value therefore remains a
two-decimal bar reading without a Python-side conversion.

## Retained safety improvements

- flow interrupts update `volatile unsigned long` pulse counters;
- the main loop snapshots and resets counters atomically;
- interrupts stay active while sensor reads and serial output run;
- thermistor and pressure ADC endpoints are rejected;
- non-finite and broadly impossible readings become `null`;
- one invalid channel does not suppress the other channels on that line.

Zero flow remains a valid measurement. Firmware cannot distinguish a connected
stationary flow meter from a disconnected meter that produces no pulses; that
requires a physical-flow or injected-pulse test.

## Build prerequisites

The expected board is an Arduino Uno. Install the Arduino AVR Boards core and,
for the pump-room sketch only, the Arduino DHT sensor library. No LabPulse
Arduino library is required.

```bash
arduino-cli compile --fqbn arduino:avr:uno pressure_monitor
arduino-cli compile --fqbn arduino:avr:uno turbo_pump
arduino-cli compile --fqbn arduino:avr:uno pump_room
```

Do not flash a live board until its stable USB identity, physical role, current
sketch, and pin wiring have been recorded. Flash one board at a time and verify
every configured key in Serial Monitor before restarting its LabPulse service.

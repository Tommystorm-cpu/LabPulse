# LabPulse Docker Refactor Documentation

This directory documents the implemented system under `docker_refactor/`.
It contains reference guides plus one maintained software roadmap. Design
proposals, completed refactor plans, and duplicate task-specific notes have
been removed so that an implemented feature has one authoritative explanation.

## Reading order

1. [ARCHITECTURE.md](ARCHITECTURE.md) explains the system at container and
   package level: what runs, how data moves, and which component owns each
   decision.
2. [CODE_INTERNALS.md](CODE_INTERNALS.md) follows the code itself: models,
   functions, runtime data structures, Home Assistant rendering, the alarm
   state machine, MQTT, SMS, and the simulator.
3. [SETUP_AND_TROUBLESHOOTING.md](SETUP_AND_TROUBLESHOOTING.md) is the operator
   guide: first installation, normal updates, fake hardware, dashboard safety,
   SMS setup, testing, and fault isolation.
4. [ARDUINO_AND_CPP.md](ARDUINO_AND_CPP.md) records the standardized Arduino
   JSON contract, the temporary legacy formats, and their migration boundary.
   The buildable sketches and shared library are in
   [`../firmware/`](../firmware/).
5. [SOFTWARE_TODO.md](SOFTWARE_TODO.md) tracks remaining reliability,
   user-facing, engineering-maturity, and open-source work.
6. [POWER_MONITOR_TEST_PI.md](POWER_MONITOR_TEST_PI.md) is the exact dry-run
   acceptance procedure for the simulated UPS power lifecycle.

Future implementation specification:

- [FUTURE_HOME_ASSISTANT_DASHBOARD_API.md](FUTURE_HOME_ASSISTANT_DASHBOARD_API.md)
  records the planned move from direct Lovelace `.storage` writes to Home
  Assistant's authenticated WebSocket API. It is intentionally deferred until
  live-Pi sensor acquisition is proven.
- [FUTURE_POWER_MONITOR_IMPLEMENTATION.md](FUTURE_POWER_MONITOR_IMPLEMENTATION.md)
  records the reviewed legacy UPS behaviour and acceptance criteria. The code
  is implemented, but this temporary file remains until test-Pi and live-Pi
  acceptance and calibration have actually been completed.

## Which guide answers what?

| Question | Guide |
| --- | --- |
| Why are there several containers and packages? | `ARCHITECTURE.md` |
| Where does a reading travel from USB to Home Assistant? | `ARCHITECTURE.md`, then `CODE_INTERNALS.md` |
| Which model contains a service, reading, or entity ID? | `CODE_INTERNALS.md` |
| How are `[[ ... ]]` and `{{ ... }}` different? | `CODE_INTERNALS.md` |
| How does Normal/Danger/Sensor Fault work? | `CODE_INTERNALS.md` |
| What do I edit on the Raspberry Pi? | `SETUP_AND_TROUBLESHOOTING.md` |
| How do I identify and assign the real USB devices? | `SETUP_AND_TROUBLESHOOTING.md` |
| How do I test without hardware? | `SETUP_AND_TROUBLESHOOTING.md` |
| How do I accept the simulated UPS lifecycle? | `POWER_MONITOR_TEST_PI.md` |
| Why is an entity or dashboard card missing? | `SETUP_AND_TROUBLESHOOTING.md` |
| What exactly do the Arduino sketches print? | `ARDUINO_AND_CPP.md` |
| What software work remains and what is already implemented? | `SOFTWARE_TODO.md` |
| How should dashboard deployment avoid `.storage` ownership problems? | `FUTURE_HOME_ASSISTANT_DASHBOARD_API.md` |

## Sources of truth

There are three kinds of configuration; confusing them causes most setup
problems.

| Concern | Source of truth |
| --- | --- |
| Running Pi services, hardware, labels, and recipients | `~/labpulse-ha/config.yaml` |
| Initial per-reading Min, Max, and Deadband | `~/labpulse-ha/alarm_defaults.json` |
| Fresh-install starter values | repository `docker_refactor/config.yaml` and `alarm_defaults.json` |
| Live dashboard arrangement and helper values | Home Assistant UI/state |
| Generated starter dashboard structure | `labpulse_homeassistant/templates/dashboard/dashboard_seed.yaml` |
| Generated alarm behavior | `labpulse_homeassistant/templates/alarm/alarm_logic.yaml` |
| Generated UPS power lifecycle | `labpulse_homeassistant/templates/alarm/power_logic.yaml` |

Do not hand-edit `compose.yaml`, `labpulse_generated.yaml`, or
`labpulse_entity_map.yaml` as permanent changes. They are generated outputs.

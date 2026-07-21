# LabPulse Docker Refactor Documentation

This directory documents the implemented system under `docker_refactor/`.
It contains reference guides plus one maintained software roadmap. Design
proposals, completed refactor plans, and duplicate task-specific notes have
been removed so that an implemented feature has one authoritative explanation.

## Documentation order

1. [ARCHITECTURE.md](ARCHITECTURE.md) explains the system at container and
   package level: what runs, how data moves, and which component owns each
   decision.
2. [CODE_INTERNALS.md](CODE_INTERNALS.md) follows the code itself: models,
   functions, runtime data structures, Home Assistant rendering, the alarm
   state machine, MQTT, SMS, and the simulator.
3. [HOME_ASSISTANT_RENDER_MODELS.md](HOME_ASSISTANT_RENDER_MODELS.md) is the
   field-by-field reference for the Home Assistant dataclasses, their
   containment hierarchy, and the values consumed by each writer.
4. [SETUP_AND_TROUBLESHOOTING.md](SETUP_AND_TROUBLESHOOTING.md) is the operator
   guide: first installation, normal updates, fake hardware, dashboard safety,
   SMS setup, testing, and fault isolation.
5. [ARDUINO_AND_CPP.md](ARDUINO_AND_CPP.md) records the standardized Arduino
   pipe-delimited contract, temporary legacy formats, and migration boundary.
   The buildable sketches and shared library are in
   [`../firmware/`](../firmware/).
6. [SOFTWARE_TODO.md](SOFTWARE_TODO.md) tracks remaining reliability,
   user-facing, engineering-maturity, and open-source work.
7. [POWER_MONITOR_TEST_PI.md](POWER_MONITOR_TEST_PI.md) is the exact dry-run
   and live GPIO acceptance procedure for the X1200 power lifecycle.

Approved implementation specification:

- [HOME_ASSISTANT_YAML_DASHBOARD_REFACTOR.md](HOME_ASSISTANT_YAML_DASHBOARD_REFACTOR.md)
  records the completed YAML-mode dashboard, logical setup grouping, physical
  sensor-hub diagnostics, and notification-context refactor.

## Which guide answers what?

| Question | Guide |
| --- | --- |
| Why are there several containers and packages? | `ARCHITECTURE.md` |
| Where does a measurement travel from USB to Home Assistant? | `ARCHITECTURE.md`, then `CODE_INTERNALS.md` |
| Which model contains a service, measurement, or entity ID? | `HOME_ASSISTANT_RENDER_MODELS.md` |
| Which Python file produces each Home Assistant resource? | [`labpulse_homeassistant/README.md`](../labpulse_homeassistant/README.md#generation-flow) |
| How are `[[ ... ]]` and `{{ ... }}` different? | `CODE_INTERNALS.md` |
| How does Normal/Danger/Sensor Fault work? | `CODE_INTERNALS.md` |
| What do I edit on the Raspberry Pi? | `SETUP_AND_TROUBLESHOOTING.md` |
| How do I identify and assign the real USB devices? | `SETUP_AND_TROUBLESHOOTING.md` |
| How do I test without hardware? | `SETUP_AND_TROUBLESHOOTING.md` |
| How do I accept the X1200 UPS lifecycle? | `POWER_MONITOR_TEST_PI.md` |
| Why is an entity or dashboard card missing? | `SETUP_AND_TROUBLESHOOTING.md` |
| What exactly do the Arduino sketches print? | `ARDUINO_AND_CPP.md` |
| What software work remains and what is already implemented? | `SOFTWARE_TODO.md` |
| How do setup grouping and YAML dashboard generation work? | `HOME_ASSISTANT_YAML_DASHBOARD_REFACTOR.md` |

## Sources of truth

There are three kinds of configuration; confusing them causes most setup
problems.

| Concern | Source of truth |
| --- | --- |
| Running Pi services, hardware, labels, and recipients | `~/labpulse-ha/config.yaml` |
| Fresh-install deployment starter | repository `docker_refactor/config.yaml` |
| Setup membership, subcategories, and generated dashboard arrangement | `~/labpulse-ha/config.yaml` plus `labpulse_homeassistant/dashboard/` |
| Thresholds, alarm modes, mute state, and other live alarm controls | Home Assistant state and the Alarm Setup dashboard |
| All user-facing SMS wording | `labpulse_common/sms_templates.yaml` |
| Generated dashboard fragments | `labpulse_homeassistant/templates/dashboard/` |
| Generated alarm behavior | `labpulse_homeassistant/templates/alarm/alarm_logic.yaml` |
| Generated UPS power lifecycle | `labpulse_homeassistant/templates/alarm/power_logic.yaml` |

Do not hand-edit `compose.yaml`, `labpulse_generated.yaml`, or
`labpulse-dashboard.yaml` as permanent changes.
They are generated outputs.

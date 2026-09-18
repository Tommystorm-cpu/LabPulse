INTERNSHIP PORTFOLIO  /  LAIRD GROUP  /  LANCASTER UNIVERSITY

# LabPulse internship achievements

Tommy Davey

Developing a configurable laboratory monitoring platform

My internship work developed LabPulse from a collection of monitoring scripts into a more maintainable system for laboratory infrastructure. I built on the existing Raspberry Pi, Arduino and Home Assistant prototype, adding a consistent architecture, richer alarms, clearer diagnostics and a repeatable installation workflow. Alongside the software, I designed and prototyped an enclosure and developed the layout for a more integrated main unit.

The result brings sensor readings, service health and operator controls into one generated dashboard. It also gives future students and researchers a practical route to configure, test, maintain and extend the system.

## Why the work matters

Experiments depend on services such as cooling water, compressed air and electrical power. LabPulse helps researchers see changing conditions and receive a warning when a confirmed problem needs attention. My work focused on making those readings easier to trust and the system easier to operate over time.

| Breadth of the current implementation | What this enables |
| --- | --- |
| 6 input driver types | Arduino serial, MQTT JSON, GPIO inputs, DHT11, SHT40 and X1200 UPS. |
| 3 main dashboard views | Monitor, System Status and Alarm Setup, with custom setup grouping and tabs. |
| 38 automated test modules | Hardware-free checks across configuration, drivers, alarms, messaging and deployment. |

## My contribution at a glance

**Software:** isolated workers, reusable firmware and generated dashboards. **Hardware:** enclosure CAD, a printed prototype and component integration. **Reliability:** richer fault reporting, power recovery and repeatable testing. **Handover:** installation commands, backup and restore, release automation and documentation.

Development record: July to September 2026. Comparison snapshot: 17 September 2026. Driver and test-module counts describe the current repository; they are not counts of connected devices or successful live tests.

01  /  BEFORE AND AFTER

# Building on the original system

The original project already delivered useful monitoring. Arduino hubs supplied compressed-air pressure and cooling-water temperature and flow; the Pi also monitored room conditions and UPS power. Readings appeared in Home Assistant and threshold or power events could trigger SMS alerts. [1]

The legacy directory contains several generations. Its later scripts already added central YAML configuration, stable USB paths, shared SMS code, recovery messages and basic heartbeats. The Future_work folder also proposed a generic driver architecture. My work developed these foundations into the current implementation. [2, 3]

| Area | Legacy capability | Current implementation |
| --- | --- | --- |
| Deployment | Individual Python scripts, virtual environments and systemd services; setup scripts. | A packaged command-line tool and generated Docker Compose deployment with isolated workers. |
| Configuration | Fixed service sections in YAML plus a separate thresholds file. | Validated services, measurement defaults and optional measurement files generate runtime and dashboard configuration. |
| Dashboard | MQTT sensor discovery and some threshold controls. | Generated Monitor, System Status and Alarm Setup views, history graphs, custom tabs and setup grouping. |
| Alarm decisions | Script-specific threshold checks; later publishers count consecutive readings. | Low, high or range alarms, time-based confirmation, recovery delay and deadband to reduce repeated alerts. |
| Fault diagnosis | Reconnect loops and periodic Online heartbeats. | Separate service availability, partial faults and missing readings; recovery needs appropriate fresh evidence. |
| Notifications | SMS and recovery messages, with sender threads in the monitoring scripts. | One SMS worker, duplicate suppression, test recipients, mutes and subscription controls. |
| Extension and upkeep | Device-specific parsers, sketches and a proposed master hub. | Reusable drivers and firmware, network inputs, diagnostics, simulation, backup and restore, and release workflows. |

The main improvement is the consistency of the whole system: adding or changing a measurement can update its deployment, dashboard and alarm configuration through the same validated model. [4, 5]

02  /  ENGINEERING CONTRIBUTIONS

# What I implemented

## A consistent route from hardware to the dashboard

I separated hardware acquisition, dashboard generation, alarm decisions and SMS delivery. Docker containers give each enabled service its own runtime, while a shared runner handles connection, retries, reading freshness and cleanup. Drivers follow the same connect, read and close contract and declare the hardware access they need. [4]

Architecture diagram: Sensors and PCs -> LabPulse workers -> Home Assistant, with MQTT carrying readings and health. Home Assistant requests SMS delivery and sends manual output commands.

## Broader hardware and instrument integration

I implemented support for standard serial readings, direct temperature and humidity sensors, X1200 battery and mains monitoring, named network measurements and generic digital inputs. I rewrote the Arduino firmware around reusable pressure, flow, thermistor and environmental-sensor components, with three hub examples and one consistent serial format. Missing channels can be reported without discarding the remaining readings. [4, 6]

For Triton fridges, I added Windows publishers that decode binary logfiles and send named measurements over MQTT. The production publisher includes reconnection, logging and independent heartbeats, allowing script health to be tracked separately from the age of the latest reading. The network path supports authenticated, encrypted connections. [7]

## Alarms that explain what needs attention

I developed configurable threshold modes, observation windows, recovery timing and deadband. The dashboard distinguishes an out-of-range value from missing data, a partial sensor fault and a whole service going offline. Service-level reporting avoids a separate missing-data alert for every channel when an entire hub disappears. [5]

I added calculated measurements, logical setup grouping, graphs and bulk timing controls. Notification controls include global and setup mutes, test-recipient routing and inbound subscription commands. A central SMS worker serializes modem access and suppresses repeated requests. [5, 8]

## Controlled outputs with an explicit scope

I added manual GPIO switches with safe-state handling on startup, shutdown and connection loss, plus an optional maximum active time. GPIO readback checks the Pi output state; it does not prove that attached equipment moved. These controls remain separate from alarm-driven automation. [9]

03  /  HARDWARE AND ENCLOSURE

# Designing the physical system

My contribution also covered the practical packaging of LabPulse. I worked on how the Pi, backup power, modem, sensor connections and local interface could fit together as a serviceable laboratory unit. This involved CAD layout, mounting choices, cable access and testing a printed enclosure. [14]

## From CAD to a physical prototype

I developed an enclosure around the Pi stack and an adjacent housing for the Gravity IO expansion board, including the opening for its ribbon cable. I considered board clearance, port access, fixing positions and how the parts would be oriented for printing.

I had the parts printed and checked their fit. The locating lip was snug enough to hold the case together, while a thin snap clip broke and sections of the lip needed more strength. That gave me concrete feedback for the next design iteration: preserve the useful mating clearance while improving the strength of the retaining features.

## Developing an integrated wall unit

I then developed the design direction for a shallow, wall-mounted enclosure with a 7-inch touchscreen. The layout brought together the Pi 5 and X1200 UPS, active cooler, cellular modem, Gravity board and powered USB hub. I explored component placement, consistent screw and standoff fixings, and retaining bars for the display.

| Design decision | Practical reason |
| --- | --- |
| Removable front assembly and passive wall plate | Keep the electronics together so short internal USB cables do not tie opposite halves of the case together. |
| Top-facing USB connections | Make the removable Arduino leads accessible while keeping permanent modem wiring inside. |
| Gravity board on a GPIO ribbon | Place sensor connections where they can be reached without making the Pi stack taller. |

## Hardware integration and engineering judgement

I investigated the mismatch between the purchased Gravity board and its adapter cable, and worked through the connector arrangement for the room sensor. The enclosure work required balancing physical fit, cable bends, cooling, accessibility and straightforward assembly, rather than treating the electronics as separate boards.

The printed Pi-stack enclosure is a prototype result. The later touchscreen enclosure is documented design work, with final assembly and fit checks still to be recorded. The older STLs in the repository are separate inherited assets. [14]

04  /  RELIABILITY AND HANDOVER

# Making the work maintainable

## Installation and everyday operation

I created the labpulse command interface for setup, startup, status, logs, configuration and diagnostics. The doctor command checks common installation and runtime problems and suggests corrective actions. Guarded configuration regenerates the derived files, and backup and restore preserve configuration, Home Assistant state, retained MQTT data and SMS subscription state. [10]

## Testing and release engineering

I added full fake-hardware operation so the configured dashboards, sensor workers and output switches can be exercised without physical devices; SMS is logged rather than sent. The repository contains 38 automated test modules and continuous-integration workflows for Python 3.11 and 3.12. Release automation checks installable packages and containers, aligns versions with Git tags and defines publication to PyPI and the container registry. [11]

## Recorded installation evidence

The project roadmap records acceptance on 27 July 2026 for the Raspberry Pi 5 reference installation at revision dc6c29f. It reports two weeks of continuous operation, unplug and reconnect tests, injected sensor faults, container and Pi restarts, real UPS outages, abrupt power removal, and SMS delivery and recovery without loss of user-owned state. [12]

That work also isolated recurring USB disconnects to a faulty external hub and identified a DHT11 that could remain unresponsive after a brief power interruption. Separating those hardware defects from software behaviour is part of the engineering result. The July acceptance record applies to that revision; later SHT40, Triton, GPIO and dashboard work needs its own installation checks. [12]

## Documentation and continuity

I expanded the documentation into first steps, installation, configuration, operation, troubleshooting, hardware, firmware, development and maintenance guides. I also added examples, release guidance and a screenshot checklist, and recorded the main-unit parts and enclosure design history so the next maintainer can continue the work. [6, 13, 14]

## Skills demonstrated

Python architecture; embedded C++ firmware; Linux and Docker; MQTT integration; Home Assistant interfaces; CAD and enclosure design; 3D-print prototyping; hardware integration; fault diagnosis; automated testing; release engineering; and technical communication.

LabPulse remains a monitoring and notification aid. Its engineering scope does not include a safety interlock or guaranteed SMS delivery.

**Evidence guide**  [1] legacy README, setup guide and flowchart. [2] legacy/pi_scripts and its shared library. [3] legacy/Future_work. [4] src/labpulse/common, hardware and deployment. [5] homeassistant package and User Guide. [6] firmware and hardware guides. [7] Triton publishers and guide. [8] sms package. [9] output package. [10] control.py, doctor.py and backup.py. [11] testing and .github/workflows. [12] ROADMAP.md, Stage 1. [13] docs and screenshot.md. [14] MAIN_UNIT.md and the July to August enclosure design discussions. Full references accompany the editable report.

## Review scope and source references

Prepared for Tommy Davey from the working tree on 17 September 2026, based on commit `44a7445`, including existing uncommitted documentation changes. As requested, the comparison target is the new repository. Current-source capabilities and the earlier recorded installation acceptance are identified separately.

The July to September period is the development period visible in Git history, not a confirmed contractual internship date range. The author name was supplied by Tommy Davey, and the recent implementation is attributed in Git to Tommy. The counts are six input drivers (excluding the GPIO output driver), three main generated dashboard views and 38 `testing/test_*.py` modules. No claim is made that the test suite was rerun for this document.

- [1] [Legacy overview](../../legacy/LEGACY%20README.md), [original setup guide](../../legacy/Documentation/Setup%20of%20a%20lab%20monitor%20on%20a%20raspberry%20pi.docx), [original system flowchart](../../legacy/Set_up_flowchart.pdf), and [archived publishers](../../legacy/archive_v1_pi_code/).
- [2] [Later legacy publishers](../../legacy/pi_scripts/), particularly pressurepub.py, pumproompub.py, turbo_pump_monitor.py, powerpub.py, dhtpub.py, and labpulse_common/{config,mqtt_health,sms}.py. These already contain central configuration, basic validation, threshold persistence, stable serial paths and shared alerting. Private contact values are intentionally excluded from the report.
- [3] [Proposed universal hub](../../legacy/Future_work/README_FW.md), main.py, sensor_base.py and sensor_factory.py; [May 2026 project review](../../legacy/Documentation/PROJECT_REVIEW.md).
- [4] [Architecture](../ARCHITECTURE.md), [hardware runner](../../src/labpulse/hardware/runner.py), [driver definitions](../../src/labpulse/hardware/drivers/README.md), [configuration models](../../src/labpulse/common/) and [deployment generation](../../src/labpulse/deployment/).
- [5] [User Guide](../USER_GUIDE.md), [Home Assistant generation](../../src/labpulse/homeassistant/), [measurement configuration](../../src/labpulse/common/measurement_config.py). Alarm confirmation is based on time in the observation window, not sample count.
- [6] [Firmware library and examples](../../firmware/README.md), [hardware guide](../HARDWARE.md). Earlier PCB work predates the current internship development commits; no fabrication, calibration or electrical qualification is inferred.
- [7] [Triton integration guide](../TRITON_PUBLISHER.md), [setup publisher](../../firmware/triton_logfile_publisher_setup.py) and [production publisher](../../firmware/triton_logfile_publisher_production.py).
- [8] [SMS worker](../../src/labpulse/sms/README.md), sender.py and subscriber.py. Dry-run and dashboard Test mode have different effects: Test mode may send real SMS to test recipients.
- [9] [Output worker](../../src/labpulse/output/README.md) and [GPIO output driver](../../src/labpulse/hardware/drivers/gpio_output.py).
- [10] [Operator command](../../src/labpulse/control.py), [diagnostics](../../src/labpulse/doctor.py), [backup and restore](../../src/labpulse/backup.py), [installation](../INSTALLATION.md) and [package metadata](../../pyproject.toml).
- [11] [Tests](../../testing/), [CI workflow](../../.github/workflows/test.yml), [release workflow](../../.github/workflows/release.yml), [simulation](../../src/labpulse/hardware/_simulation.py) and [fake configuration](../../src/labpulse/common/fake_config.py). Workflow definitions are evidence of implemented automation, not proof of the latest remote publishing result.
- [12] [Roadmap](../../ROADMAP.md), specifically Current source status and Stage 1 real-hardware reliability. The recorded acceptance is dated 27 July 2026 at `dc6c29f`; it is distinct from the 17 September source snapshot.
- [13] [Documentation index](../README.md), [screenshot checklist](../../screenshot.md), [contributing guide](../../CONTRIBUTING.md) and [changelog](../../CHANGELOG.md). This report introduces no screenshot or photo insertion points, so the existing capture checklist requires no changes.
- [14] [Main unit and enclosure history](../MAIN_UNIT.md#enclosure-history), plus the Codex tasks **Find Gravity HAT mounting clearance** (`019fb249-8b04-7021-b281-c240d249e170`, 30 July to 3 August 2026) and **Resolve Gravity IO cable mismatch** (`019fcbf2-effe-7bc3-9b20-082d3526ec20`, 4 to 5 August 2026). The first includes Tommy's confirmation that he printed the parts and assessed the lip and broken clip. The second records the later touchscreen design discussion. Final manufacturing dimensions, a completed touchscreen build, and the implementation of every suggested revision are not inferred.

Git milestones supporting the contribution narrative: `491befb` Docker setup; `8ef5335` USB robustness; `d5a0f03` structural refactor; `6e05b60` alarm logic; `ea4abcc` power driver; `e35199e` firmware rewrite; `d12616c` driver API; `68e23ee` packaging; `577cdf5` CLI; `b1f70ed` backup/restore; `d6030c6` distribution; `ded77e1` tests; `d301de0` SHT40; `116f4e0` network MQTT; `5dc6db0` GPIO; `4529ce3` sensor faults; `5022de5` fridge networking; `b646f0f` publisher heartbeat; `17f2234` full simulation; `44a7445` documentation.

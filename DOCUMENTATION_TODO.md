# Documentation still to finish

The remaining work is small. These guides should help another lab install
LabPulse and connect its own sensors; they don't need a complete record of
how our lab is wired.

## Main tasks

- [ ] **Add the three simulated walkthrough screenshots.** Follow [screenshot.md](screenshot.md)
  for the Monitor, System Status, and Alarm Setup captures. Replace the
  placeholders and tick the entries there.
  Capture these during the planned fake-hardware run on a separate test Pi.
  Live Monitor and System Status captures are already in the README and User
  Guide as examples of the installed system's features.
- [x] **Check the hardware details that affect someone else's choices.**
  In [Hardware](docs/HARDWARE.md) and [Main unit](docs/MAIN_UNIT.md), correct any
  part names or compatibility details you know are wrong. Concentrate on useful
  gotchas such as the Gravity cable mismatch, UPS/GPIO conflicts, and hub power.
  Leave unknown models labelled unknown; no need to audit every installed sensor.
  Update recorded 18 September: X1200 confirmed; external 12 V hub supply and
  intended Pi/UPS fallback and requested parts documented. SHT40 connections
  are not installed yet; the planned Pi cable modification uses one soldered
  four-position female header. The display is a 7-inch Touch Display 2 with
  standoffs removed. The case is printed, awaiting parts before assembly.
  Cable assembly and outage behaviour remain labelled as plans until checked.
  All three workbooks reviewed: flow-sensor purchase links identify
  SEN0217/YF-S201; pump-room pressure models remain explicitly unknown.
- [x] **Give the Arduino instructions a quick sanity check.** Read the
  [firmware guide](firmware/README.md) and [first-sensor walkthrough](docs/FIRST_SENSOR.md).
  Add anything a reader couldn't infer from the pin assignments and examples,
  especially sensor-specific conversion values. Full circuit drawings aren't
  required for straightforward wiring.
  Conversion provenance recorded from the original code: 0.48 V is labelled
  as the calibrated atmospheric-pressure voltage, thermistor coefficients came
  from Python fitting with retained datasheet points, and flow agrees with the
  manufacturer's nominal 450 pulses/litre. The thermistor script does not name
  its datasheet; the old 2.2 kΩ and current 4.7 kΩ divider examples are distinguished.
  Conversation history confirms the maintainer flashed each LabPulseFirmware
  example on 22 July 2026 and reported it working. Library-discovery guidance
  and serial-port ownership during upload are clarified. Later firmware changes
  are not claimed to have been flashed.
- [ ] **Read through the beginner instructions once.** Check
  [Installation](docs/INSTALLATION.md) and [First steps](docs/FIRST_STEPS.md)
  against how you actually use LabPulse. Fix missing steps or misleading
  wording you notice. This doesn't need a formal test report.
  The maintainer plans to follow the walkthrough on a separate test Pi in
  fake-hardware mode; the run has not yet been completed.
  The installation guide now spells out OS preparation, Docker installation,
  automatic Home Assistant/Mosquitto deployment, time-service choices, optional
  host ModemManager setup, and a reboot check. These steps still need that Pi run.

## Optional extras

- Add a clear photo of a sensor hub and the main unit if it helps readers
  understand the hardware. The optional capture slots are in
  [screenshot.md](screenshot.md).
- The [enclosure CAD](hardware/enclosure/README.md) now includes the Fusion
  assembly and STEP export. If others should reproduce the print, identify the
  printed CAD revision, add the individual print files and settings, and record
  parts, fasteners, and assembly. Fit and assembly are still unverified; see
  [Main unit](docs/MAIN_UNIT.md#finish-the-build-record).
- If someone new tries the user or maintainer guides, use their questions to
  improve the wording. A formal handover exercise isn't a requirement.

Lab-specific plumbing, cable inventories, battery replacement histories,
commissioning reports, and a full record of the installed wiring are outside
this documentation checklist. Each lab will make its own installation choices.

After editing, run this from the repository root:

```bash
python -m pytest testing/test_documentation.py -q
```

Keep this list short. Add an item only when it fills a useful gap for a user
or maintainer, and keep image tasks in sync with [screenshot.md](screenshot.md).

# Screenshots and photos to add

This checklist tracks documentation captures, including those already added.
Each link opens the image or its marked insertion point. Replace a placeholder
with the image and a short caption when it's ready, then tick the item here.

For the other remaining documentation tasks, use
[the manual documentation checklist](DOCUMENTATION_TODO.md).

## Live installation screenshots

- [x] **[Monitor: live installation overview](README.md#live-installation).**
  Real capture of the live reference installation supplied 18 September 2026,
  with the account sidebar removed. Shows readings grouped by setup, UPS power,
  and the Test mode banner.
  File: `docs/images/live-monitor.png`.
  LabPulse and Home Assistant versions were not supplied; add them when known.
- [x] **[System Status: service health and optional readings](docs/USER_GUIDE.md#system-status).**
  Real capture of the live reference installation supplied 18 September 2026.
  Shows three working sensor hubs and two absent optional temperature readings.
  File: `docs/images/live-system-status.png`.
  LabPulse and Home Assistant versions were not supplied; add them when known.

## First Steps screenshots (simulation)

Capture these on the separate test Pi using fake-hardware mode and the starter
configuration, so the images match the walkthrough.

- [ ] **[Monitor: find a reading](docs/FIRST_STEPS.md#1-find-a-reading).**
  Show Compressed Air and its simulated pressure reading. Identify the reading
  to select for history.
  Suggested filename: `docs/images/first-steps-monitor.png`.
- [ ] **[System Status: check the service](docs/FIRST_STEPS.md#2-check-the-service).**
  Show Compressed Air and Environment Sensor Hub reporting Working, with its
  latest readings. Mark the service name, status, and reading timestamps.
  Suggested filename: `docs/images/first-steps-system-status.png`.
- [ ] **[Alarm Setup: make a practice alarm](docs/FIRST_STEPS.md#3-make-a-practice-alarm).**
  Open Configure for Compressed Air, then Configure beside pressure. Show
  Alarm mode, Maximum threshold, Recovery deadband, Required danger,
  Observation window, and Required recovery. Use the practice settings in the
  walkthrough, with notifications muted.
  Suggested filename: `docs/images/first-steps-alarm-setup.png`.

## Contributor screenshots

- [ ] **[GitHub: open a sensor pull request](CONTRIBUTING.md#4-open-a-pull-request-into-labpulse).**
  Replace the “Screenshot to add: contributing from a fork” block. Show
  `lairdgrouplancaster/LabPulse` and `main` as the base, and a real contributor
  fork and sensor branch as the head. Obtain permission to show the account
  name and crop unrelated account details. Record the capture date because
  GitHub's interface can change.
  Suggested filename: `docs/images/contributing-sensor-pull-request.png`.

## Hardware photos (optional)

These help readers recognise the main parts. Use real hardware and explain
what is shown; a complete wiring record isn't needed.

- [ ] **[Verified sensor hub](docs/HARDWARE.md#existing-hardware-assets)** —
  replace the “Photo to add: one verified sensor hub” block. Show the board,
  main parts, connectors, and USB connection. Name the firmware example it uses
  and any differences from its pin assignments.
  Suggested filename: `docs/images/hardware-sensor-hub.jpg`.
- [ ] **[Assembled installation](docs/MAIN_UNIT.md#finish-the-build-record)** —
  replace the “Photo to add: the assembled installation” block. Show the open
  main unit with its principal boards and connections. Add a closed-case view
  if useful. Identify any pictured prototype or planned part so readers know
  what they are looking at. If the display is shown, identify the 7-inch Touch
  Display 2 with its removed standoffs and show how the case supports it.
  Waiting for assembly: the current case is printed, but key parts have not
  arrived yet.
  Suggested filename: `docs/images/hardware-installation.jpg`.

## When adding an image

Use example data where possible. Check for phone numbers, account details,
private addresses, and other lab information before committing a capture.
Keep text large enough to read and crop out unrelated browser or desktop UI.

Store the image under `docs/images/`. In the guide, use a relative Markdown
image link with useful alternative text, followed by a short caption explaining
what to notice. For dashboard captures, record the LabPulse and Home Assistant
versions used so a future maintainer can tell when the image needs refreshing.

## Keep this list current

The [maintainer exercises](docs/MAINTAINER_EXAMPLES.md#change-a-dashboard-heading)
explain how to check a dashboard change before deciding which images need a
new capture. They currently add no separate screenshot slots.

Whenever documentation changes add, move, or remove an image insertion point,
update this checklist in the same change. Keep links pointing to the right
sections. Tick completed entries only once the actual image is in the guide;
if a later interface change makes it misleading, untick it and explain what
needs recapturing. Remove entries for sections that no longer need an image.

Run `python -m pytest testing/test_documentation.py -q` to check the links after
editing. This file tracks planned captures; don't add image links for files
that don't exist yet.
